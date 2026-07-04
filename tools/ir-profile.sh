#!/usr/bin/env bash
# tools/ir-profile.sh
# Deep IR static analysis for the CMA engine.
# Usage: bash tools/ir-profile.sh [path/to/pfun_cma_engine.ll]

set -euo pipefail

IR="${1:-build/pfun_cma_engine.ll}"

if [ ! -f "$IR" ]; then
    echo "❌ IR file not found: $IR"
    echo "   Run 'make llvm-ir' first."
    exit 1
fi

echo "═══════════════════════════════════════════════════════════════════"
echo "  IR Static Profile — CMA Engine"
echo "  Source: $IR"
echo "═══════════════════════════════════════════════════════════════════"
echo ""

# ── 1. Module overview ──
echo "── 1. Module Overview ──"
echo "  Target:        $(grep 'target triple' "$IR" | head -1 | sed 's/.*= "//;s/"$//')"
echo "  Data layout:   $(grep 'target datalayout' "$IR" | head -1 | sed 's/.*= "//;s/"$//')"
echo "  Clang version: $(grep 'clang version' "$IR" | head -1 | sed 's/.*!//;s/"//g')"
echo ""

# ── 2. Function profile ──
echo "── 2. Function Profile ──"

extract_func_body() {
    local func="$1" infile="$2"
    awk -v f="$func" '
        /^define / { in_func = 0 }
        index($0, "@" f "(") { in_func = 1; print; next }
        in_func { print }
    ' "$infile"
}

TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

# Split IR per function
csplit -s -z -f "$TMPDIR/fn_" "$IR" '/^define /' '{*}' 2>/dev/null || true

printf "  %-32s %5s %5s %6s %6s %5s %5s %5s\n" \
    "Function" "Instrs" "Blks" "FmulAdd" "FPadd" "FPmul" "Fdiv" "FLOPs"
printf "  %-32s %5s %5s %6s %6s %5s %5s %5s\n" \
    "──────────────────────────────" "─────" "─────" "──────" "──────" "─────" "─────" "─────"

total_instrs=0
total_fma=0
total_fpadd=0
total_fpmul=0
total_fpdiv=0

for fnfile in "$TMPDIR"/fn_*; do
    [ -f "$fnfile" ] || continue
    funcname=$(grep '^define ' "$fnfile" | sed 's/.*@//;s/(.*//' | head -1) || true
    [ -n "$funcname" ] || continue

    instrs=$(grep -cE '^\s+\w' "$fnfile" || true)
    blocks=$(grep -cE '^[a-zA-Z_.$][a-zA-Z0-9_.$]*:' "$fnfile" || true)
    fma=$(grep -c 'fmuladd' "$fnfile" || true)
    # Count fadd/fsub as fp-add, fmul as fp-mul, fdiv as fp-div
    fpadd=$(grep -cE 'fadd|fsub' "$fnfile" || true)
    fpmul=$(grep -cE '\bfmul\b' "$fnfile" || true)
    # Exclude fmuladd from the mul count since it's separately counted
    fpdiv=$(grep -cE '\bfdiv\b' "$fnfile" || true)
    flops=$(( fpadd + fpmul + fpdiv + fma * 2 ))  # fmuladd = 2 FLOPs

    printf "  %-32s %5s %5s %6s %6s %5s %5s %5s\n" \
        "$funcname" "$instrs" "$blocks" "$fma" "$fpadd" "$fpmul" "$fpdiv" "$flops"

    total_instrs=$(( total_instrs + instrs ))
    total_fma=$(( total_fma + fma ))
    total_fpadd=$(( total_fpadd + fpadd ))
    total_fpmul=$(( total_fpmul + fpmul ))
    total_fpdiv=$(( total_fpdiv + fpdiv ))
done

total_flops=$(( total_fpadd + total_fpmul + total_fpdiv + total_fma * 2 ))
echo ""
printf "  %-32s %5s %5s %6s %6s %5s %5s %5s\n" \
    "TOTAL" "$total_instrs" "—" "$total_fma" "$total_fpadd" "$total_fpmul" "$total_fpdiv" "$total_flops"
echo ""

# ── 3. Vectorization analysis ──
echo "── 3. Vectorization Analysis ──"
vec_count=$(grep -c '<[0-9]\+ x double>' "$IR" || true)
vec_loops=$(grep -c 'llvm.loop.isvectorized' "$IR" || true)
echo "  Vector instructions (<N x double>): $vec_count"
echo "  Vectorized loops:                   $vec_loops"
echo "  Vector width:                       2 (SSE2 <2 x double>)"
echo "  Potential speedup (ideal):          ~2× vs scalar"
echo ""

# ── 4. Memory access analysis ──
echo "── 4. Memory Access Analysis ──"
loads=$(grep -cE '^\s+%[^=]+=\s+load ' "$IR" || true)
stores=$(grep -cE '^\s+store ' "$IR" || true)
mem_ops=$(( loads + stores ))
alloca=$(grep -c 'alloca ' "$IR" || true)
gep=$(grep -c 'getelementptr ' "$IR" || true)
echo "  Loads:           $loads"
echo "  Stores:          $stores"
echo "  Total mem ops:   $mem_ops"
echo "  Allocas:         $alloca"
echo "  GEPs:            $gep"
echo "  TBAA metadata:   $(grep -c '!tbaa' "$IR" || true)"
echo ""

# ── 5. Call graph ──
echo "── 5. Call Graph ──"
echo "  Internal calls (defined in module):"
internal_calls=$(grep -o '@[a-zA-Z_][a-zA-Z0-9_]*' "$IR" | sort -u | grep -v '^@llvm\.' | grep -v '^@\.str' | while read sym; do
    sym_no_at="${sym#@}"
    if grep -q "^define .* @$sym_no_at(" "$IR" 2>/dev/null; then
        echo "    $sym_no_at"
    fi
done)
if [ -n "$internal_calls" ]; then
    echo "$internal_calls"
else
    echo "    (none called)"
fi

echo ""
echo "  External library dependencies:"
for dep in exp pow log cos malloc free; do
    count=$(grep -c "@$dep" "$IR" || true)
    [ "$count" -gt 0 ] && echo "    @$dep — $count call sites"
done
echo ""

# ── 6. Arithmetic intensity estimate ──
echo "── 6. Arithmetic Intensity Estimate ──"
# Rough estimate: FLOPs / bytes loaded+stored
# Each double load/store = 8 bytes
mem_bytes=$(( mem_ops * 8 ))
if [ "$mem_bytes" -gt 0 ]; then
    intensity=$(echo "scale=2; $total_flops / $mem_bytes" | bc 2>/dev/null || echo "N/A")
    echo "  FLOPs:          $total_flops"
    echo "  Memory ops:     $mem_ops"
    echo "  Mem bytes:      $mem_bytes (assuming 8B/double)"
    echo "  Arithmetic int: $intensity FLOPs/byte"
fi
echo ""

echo "═══════════════════════════════════════════════════════════════════"
