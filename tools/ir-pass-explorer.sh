#!/usr/bin/env bash
# tools/ir-pass-explorer.sh
# Explore individual LLVM opt pass effects on the CMA engine IR.
# Usage: bash tools/ir-pass-explorer.sh [path/to/pfun_cma_engine.ll]

set -euo pipefail

IR="${1:-build/pfun_cma_engine.ll}"
TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

if [ ! -f "$IR" ]; then
    echo "❌ IR file not found: $IR"
    echo "   Run 'make llvm-ir' first."
    exit 1
fi

if ! command -v opt &>/dev/null; then
    echo "❌ 'opt' not found on PATH. Install LLVM tools."
    exit 1
fi

echo "═══════════════════════════════════════════════════════════════════"
echo "  LLVM opt Pass Explorer — CMA Engine IR"
echo "  Source: $IR"
echo "═══════════════════════════════════════════════════════════════════"
echo ""

# ── Metrics helpers ──

count_instrs() { grep -cE '^\s+\w' "$1" || true; }
count_blocks() { grep -cE '^[a-zA-Z_.$][a-zA-Z0-9_.$]*:' "$1" || true; }
count_funcs() { grep -cE '^define ' "$1" || true; }
count_fma()   { grep -c 'llvm.fmuladd' "$1" || true; }
count_vec()   { grep -c 'llvm.loop.isvectorized' "$1" || true; }
count_vec_ops() { grep -cE '<[0-9]+ x double>' "$1" || true; }

report_metrics() {
    local label="$1" infile="$2"
    local instrs blocks funcs fma vecs vecops
    instrs=$(count_instrs "$infile")
    blocks=$(count_blocks "$infile")
    funcs=$(count_funcs "$infile")
    fma=$(count_fma "$infile")
    vecs=$(count_vec "$infile")
    vecops=$(count_vec_ops "$infile")
    printf "  %-28s  %6s  %5s  %4s  %4s  %5s  %5s\n" \
        "$label" "$instrs" "$blocks" "$funcs" "$fma" "$vecs" "$vecops"
}

# ── Header ──

printf "  %-28s  %6s  %5s  %4s  %4s  %5s  %5s\n" \
    "Pass Pipeline" "Instrs" "Blocks" "Fns" "FMA" "VLoops" "VxOps"
printf "  %-28s  %6s  %5s  %4s  %4s  %5s  %5s\n" \
    "──────────────────────────" "──────" "─────" "────" "────" "─────" "─────"

# ── Individual passes ──

declare -a PASSES=(
    "instcombine:instcombine"
    "gvn:gvn"
    "simplifycfg:simplifycfg"
    "licm:licm"
    "bdce:bdce"
    "adce:adce"
    "dse:dse"
    "slp-vectorizer:slp-vectorizer"
    "loop-vectorize:loop-vectorize"
    "inliner-wrapper:inliner-wrapper"
    "licm+gvn+instcombine:licm,gvn,instcombine"
    "slp+loopvec:loop-vectorize,slp-vectorizer"
)

report_metrics "baseline (no opt)" "$IR"

for entry in "${PASSES[@]}"; do
    label="${entry%%:*}"
    passes="${entry##*:}"
    out="$TMPDIR/pass_${label}.ll"
    opt -passes="$passes" -S "$IR" -o "$out" 2>/dev/null || continue
    report_metrics "$label" "$out"
done

# ── Optimization levels ──

for LVL in O1 O2 O3 Oz; do
    out="$TMPDIR/pass_${LVL}.ll"
    opt "-$LVL" -S "$IR" -o "$out" 2>/dev/null || continue
    report_metrics "-$LVL" "$out"
done

echo ""
echo "═══════════════════════════════════════════════════════════════════"
echo "  Legend: Instrs=instructions  Blocks=basic blocks  Fns=functions"
echo "  FMA=fmuladd intrinsics  VLoops=vectorized loops  VxOps=vector ops"
echo "═══════════════════════════════════════════════════════════════════"
