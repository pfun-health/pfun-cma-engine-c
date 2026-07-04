#!/usr/bin/env bash
# tools/check-ir-metrics.sh
# Validate current IR metrics against golden reference values.
# Usage: bash tools/check-ir-metrics.sh [path/to/pfun_cma_engine.ll]

set -euo pipefail

IR="${1:-build/pfun_cma_engine.ll}"
GOLDEN="${GOLDEN:-tests/ir-golden-metrics.txt}"

if [ ! -f "$IR" ]; then
    echo "❌ IR file not found: $IR"
    echo "   Run 'make llvm-ir' first."
    exit 1
fi

if [ ! -f "$GOLDEN" ]; then
    echo "❌ Golden metrics file not found: $GOLDEN"
    exit 1
fi

# ── Metric extractors ──

extract_metric() {
    case "$1" in
        function_count) 
            grep -c '^define ' "$IR" || true ;;
        external_calls)
            grep -c '^declare ' "$IR" || true ;;
        fmuladd_intrinsics)
            grep -c 'llvm.fmuladd' "$IR" || true ;;
        vector_ops)
            grep -cE '<[0-9]+ x double>' "$IR" || true ;;
        vectorized_loops)
            grep -c 'llvm.loop.isvectorized' "$IR" || true ;;
        llvm_assume)
            grep -c 'llvm.assume' "$IR" || true ;;
        sse2_width)
            grep -oP '<\K[0-9]+(?= x double>)' "$IR" | head -1 || echo "0" ;;
        total_fp_ops)
            local fpadd fpmul fpdiv fma
            fpadd=$(grep -cE 'fadd|fsub' "$IR" || true)
            fpmul=$(grep -cE '\bfmul\b' "$IR" || true)
            fpdiv=$(grep -cE '\bfdiv\b' "$IR" || true)
            fma=$(grep -c 'fmuladd' "$IR" || true)
            echo $(( fpadd + fpmul + fpdiv + fma * 2 )) ;;
        memory_ops)
            local loads stores
            loads=$(grep -cE '^\s+%[^=]+=\s+load ' "$IR" || true)
            stores=$(grep -cE '^\s+store ' "$IR" || true)
            echo $(( loads + stores )) ;;
        arithmetic_intensity)
            local flops mem_ops mem_bytes
            flops=$(extract_metric total_fp_ops)
            loads=$(grep -cE '^\s+%[^=]+=\s+load ' "$IR" || true)
            stores=$(grep -cE '^\s+store ' "$IR" || true)
            mem_ops=$(( loads + stores ))
            mem_bytes=$(( mem_ops * 8 ))
            if [ "$mem_bytes" -gt 0 ]; then
                awk "BEGIN{printf \"%.2f\", $flops / $mem_bytes}" 2>/dev/null || echo "0"
            else
                echo "N/A"
            fi ;;
        *)
            echo "unknown" ;;
    esac
}

# ── Compare with tolerance ──

check_tolerance() {
    local current="$1" expected="$2" tolerance="$3" name="$4"
    
    if [ "$tolerance" = "exact" ]; then
        if [ "$current" -eq "$expected" ] 2>/dev/null; then
            printf "  ✅ %-25s = %5s (golden: %5s) — exact\n" "$name" "$current" "$expected"
            return 0
        else
            printf "  ❌ %-25s = %5s (golden: %5s) — EXACT FAIL\n" "$name" "$current" "$expected"
            return 1
        fi
    elif [ "$tolerance" = "pct10" ]; then
        local threshold
        threshold=$(echo "scale=0; $expected * 10 / 100" | bc)
        [ "$threshold" -lt 1 ] && threshold=1
        local diff
        diff=$(echo "scale=0; $current - $expected" | bc)
        diff=${diff#-}  # absolute value
        if [ "$diff" -le "$threshold" ] 2>/dev/null; then
            printf "  ✅ %-25s = %5s (golden: %5s ±%s) — within 10%%\n" "$name" "$current" "$expected" "$threshold"
            return 0
        else
            printf "  ❌ %-25s = %5s (golden: %5s ±%s) — OUT OF TOLERANCE (diff=%s)\n" "$name" "$current" "$expected" "$threshold" "$diff"
            return 1
        fi
    fi
}

# ── Main ──

echo "═══════════════════════════════════════════════════════════════════"
echo "  IR Golden Metrics Check"
echo "  Source: $IR"
echo "  Golden: $GOLDEN"
echo "═══════════════════════════════════════════════════════════════════"
echo ""

errors=0

while IFS='=' read -r name rest; do
    # Skip comments and blank lines
    name=$(echo "$name" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
    [ -z "$name" ] && continue
    [[ "$name" == \#* ]] && continue
    
    # Parse: name = expected tolerance description...
    expected=$(echo "$rest" | awk '{print $1}')
    tolerance=$(echo "$rest" | awk '{print $2}')
    
    current=$(extract_metric "$name")
    
    if [ "$current" = "unknown" ]; then
        echo "  ⚠️  Unknown metric: $name (check extract_metric cases)"
        continue
    fi
    
    if [[ "$current" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
        check_tolerance "$current" "$expected" "$tolerance" "$name" || errors=$(( errors + 1 ))
    else
        echo "  ⚠️  Could not parse value '$current' for $name"
    fi
done < "$GOLDEN"

echo ""
if [ "$errors" -eq 0 ]; then
    echo "✅ All golden metrics match within tolerance."
else
    echo "❌ $errors metric(s) out of tolerance — investigate changes."
fi
echo "═══════════════════════════════════════════════════════════════════"

exit "$errors"
