#!/usr/bin/env python3
"""
convert-to-llvm.py: Compile the PFun CMA Engine C source to LLVM IR and bitcode.

Usage:
    python convert-to-llvm.py [source_file]

If source_file is omitted, defaults to src/pfun_cma_engine.c.
Output is written to build/pfun_cma_engine.ll and build/pfun_cma_engine.bc.
"""

import os
import shutil
import subprocess
import sys

# ── Configuration ────────────────────────────────────────────────────────────

DEFAULT_SOURCE = "src/pfun_cma_engine.c"
OUTPUT_DIR = "build"
IR_OUTPUT = os.path.join(OUTPUT_DIR, "pfun_cma_engine.ll")
BC_OUTPUT = os.path.join(OUTPUT_DIR, "pfun_cma_engine.bc")
OPT_LEVEL = "-O2"
C_STANDARD = "-std=c99"
INCLUDE_DIRS = ["-I", "src"]
# Clang flags that are always used.
BASE_CLANG_FLAGS = [
    "-S",
    "-emit-llvm",
    OPT_LEVEL,
    C_STANDARD,
    *INCLUDE_DIRS,
]


# ── Helpers ──────────────────────────────────────────────────────────────────

def _check_dependency(name: str) -> None:
    """Exit with a helpful message if *name* is not on PATH."""
    if shutil.which(name) is None:
        print(
            f"Error: '{name}' not found on PATH. "
            f"Please install LLVM / clang and ensure it is available.",
            file=sys.stderr,
        )
        sys.exit(1)


def _ensure_output_dir(directory: str) -> None:
    """Create the output directory (and parents) if it does not exist."""
    os.makedirs(directory, exist_ok=True)


def _run(cmd: list[str], description: str) -> None:
    """Run *cmd* via subprocess, raising on failure with a clear message."""
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as exc:
        print(
            f"Error: {description} failed (exit code {exc.returncode}).",
            file=sys.stderr,
        )
        sys.exit(1)


def _print_summary(source: str, ir_path: str, bc_path: str) -> None:
    """Print a terminal-width-adaptive summary table."""
    width = shutil.get_terminal_size().columns

    # Ensure a minimum width so the table is readable.
    width = max(width, 52)

    # Build the inner lines (without borders), then measure the longest.
    lines = [
        f"  C \u2192 LLVM IR Conversion Complete  ",
        f"  Source:    {source}",
        f"  LLVM IR:   {ir_path}",
        f"  Bitcode:   {bc_path}",
        f"  Opt level: {OPT_LEVEL}",
    ]
    content_width = max(len(line) for line in lines)

    # Pad every line to the same width so the box is flush.
    padded = [line.ljust(content_width) for line in lines]

    # Horizontal rules.
    top = "\u250c" + "\u2500" * content_width + "\u2510"
    sep = "\u251c" + "\u2500" * content_width + "\u2524"
    bot = "\u2514" + "\u2500" * content_width + "\u2518"

    parts = [top]
    for i, line in enumerate(padded):
        parts.append(f"\u2502{line}\u2502")
        if i == 0:
            parts.append(sep)
    parts.append(bot)

    print("\n" + "\n".join(parts))


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    # 1. Handle help flag.
    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)

    # 2. Determine source path (optional CLI argument).
    source = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SOURCE

    # 3. Guard: source file must exist.
    if not os.path.isfile(source):
        print(f"Error: source file not found: {source}", file=sys.stderr)
        sys.exit(1)

    # 4. Guard: clang must be available.
    _check_dependency("clang")

    # 5. Create output directory.
    _ensure_output_dir(OUTPUT_DIR)

    # 6. Compile to LLVM IR (.ll).
    ir_cmd = ["clang", *BASE_CLANG_FLAGS, source, "-o", IR_OUTPUT]
    _run(ir_cmd, "LLVM IR generation")

    # 7. Produce bitcode (.bc).
    if shutil.which("llvm-as") is not None:
        bc_cmd = ["llvm-as", IR_OUTPUT, "-o", BC_OUTPUT]
        _run(bc_cmd, "bitcode assembly (llvm-as)")
    else:
        print(
            "Info: 'llvm-as' not found, falling back to clang for bitcode.",
            file=sys.stderr,
        )
        bc_cmd = [
            "clang",
            "-c",
            "-emit-llvm",
            IR_OUTPUT,
            "-o",
            BC_OUTPUT,
        ]
        _run(bc_cmd, "bitcode generation (clang fallback)")

    # 8. Summary.
    _print_summary(source, IR_OUTPUT, BC_OUTPUT)

    sys.exit(0)


if __name__ == "__main__":
    main()
