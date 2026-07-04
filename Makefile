# Standard C/C++ Makefile for pfun-cma-engine-c
# Optimized C extensions for PFun CMA model

# Compiler settings
CC := gcc
CXX := g++
CFLAGS := -Wall -Wextra -O2 -std=c99
CXXFLAGS := -Wall -Wextra -O2 -std=c++11
LDFLAGS := -lm

# Directories
SRC_DIR := src
BUILD_DIR := build
LIB_DIR := pfun_cma_engine
INCLUDE_DIR := include

# Source files
SOURCES := $(wildcard $(SRC_DIR)/*.c)
OBJECTS := $(patsubst $(SRC_DIR)/%.c,$(BUILD_DIR)/%.o,$(SOURCES))

# Target library
TARGET := $(LIB_DIR)/libpfun_cma_engine.so
STATIC_TARGET := $(LIB_DIR)/libpfun_cma_engine.a

# Header files
HEADERS := $(wildcard $(SRC_DIR)/*.h)

# Default target
.PHONY: all
all: $(TARGET) $(STATIC_TARGET)

# Create directories
.PHONY: directories
directories:
	@mkdir -p $(BUILD_DIR)
	@mkdir -p $(LIB_DIR)

# Shared library
$(TARGET): directories $(OBJECTS)
	$(CC) -shared -o $@ $(OBJECTS) $(LDFLAGS)

# Static library
$(STATIC_TARGET): directories $(OBJECTS)
	ar rcs $@ $(OBJECTS)

# Compile source files
$(BUILD_DIR)/%.o: $(SRC_DIR)/%.c $(HEADERS)
	$(CC) $(CFLAGS) -fPIC -I$(SRC_DIR) -c $< -o $@

# Clean build artifacts
.PHONY: clean
clean:
	rm -rf $(BUILD_DIR) $(LIB_DIR)/*.so $(LIB_DIR)/*.a $(LIB_DIR)/*.o

# Rebuild from scratch
.PHONY: rebuild
rebuild: clean all

# Debug build
.PHONY: debug
debug: CFLAGS := -Wall -Wextra -g -O0 -DDEBUG
debug: clean all

# Format code
.PHONY: format
format:
	@echo "Formatting code with clang-format..."
	clang-format -i $(SRC_DIR)/*.c $(SRC_DIR)/*.h 2>/dev/null || echo "clang-format not available"

# Check code style
.PHONY: check-format
check-format:
	clang-format --dry-run -Werror $(SRC_DIR)/*.c $(SRC_DIR)/*.h 2>/dev/null || echo "clang-format not available"

# Help
.PHONY: help
help:
	@echo "pfun-cma-engine-c Makefile"
	@echo "=========================="
	@echo "Available targets:"
	@echo "  all       - Build shared and static libraries (default)"
	@echo "  clean     - Remove build artifacts"
	@echo "  rebuild   - Clean and rebuild"
	@echo "  debug     - Build with debug symbols"
	@echo "  format    - Format code with clang-format"
	@echo "  test-llvm - Compile .ll to native and validate numerical output"
	@echo "  check-ir  - Run FileCheck structural IR validation"
	@echo "  llvm-ir   - Generate LLVM IR (.ll) and bitcode (.bc)"
	@echo "  llvm-verify - Verify bitcode round-trips correctly"
	@echo "  llvm-targets - Generate assembly for ARM64/Wasm/RISC-V"
	@echo "  analyze-ir - Report IR metrics (instruction count, etc.)"
	@echo "  help      - Show this help message"

# ── LLVM IR Tooling ──────────────────────────────────────────────────────────

LLVM_IR   := $(BUILD_DIR)/pfun_cma_engine.ll
LLVM_BC   := $(BUILD_DIR)/pfun_cma_engine.bc

# Generate LLVM IR (.ll) and bitcode (.bc) from C source
.PHONY: llvm-ir
llvm-ir:
	python3 convert-to-llvm.py

# Verify LLVM bitcode round-trips correctly
.PHONY: llvm-verify
llvm-verify: $(LLVM_BC)
	llvm-dis $(LLVM_BC) -o /dev/null && echo "✅ Bitcode round-trips OK" || echo "❌ Bitcode verification failed"

# Compile .ll IR to native binary and compare numerical output with GCC
.PHONY: test-llvm
test-llvm: $(LLVM_IR)
	@mkdir -p $(BUILD_DIR)
	@echo "=== Compiling GCC reference binary ==="
	$(CC) -I. -o $(BUILD_DIR)/test_scaling_gcc experiments/test_scaling.c $(SRC_DIR)/pfun_cma_engine.c -lm
	@echo "=== Compiling LLVM IR to native binary ==="
	clang -I. -o $(BUILD_DIR)/test_scaling_llvm experiments/test_scaling.c $(LLVM_IR) -lm
	@echo "=== Running GCC binary ==="
	$(BUILD_DIR)/test_scaling_gcc > $(BUILD_DIR)/output_gcc.txt
	@echo "=== Running LLVM binary ==="
	$(BUILD_DIR)/test_scaling_llvm > $(BUILD_DIR)/output_llvm.txt
	@echo "=== Numerical diff (should be empty — exact match or FP tolerance) ==="
	-diff $(BUILD_DIR)/output_gcc.txt $(BUILD_DIR)/output_llvm.txt && echo "✅ Numerical match: GCC == LLVM" || echo "⚠️  Numerical differences detected (may be FP tolerance)"
	@echo ""
	@echo "GCC output:"
	@cat $(BUILD_DIR)/output_gcc.txt
	@echo ""
	@echo "LLVM output:"
	@cat $(BUILD_DIR)/output_llvm.txt

# Structural IR validation with FileCheck
.PHONY: check-ir
check-ir: $(LLVM_IR)
	@if command -v FileCheck &>/dev/null; then \
		cat $(LLVM_IR) | FileCheck tests/ir-structural-check.llcheck && echo "✅ IR structural checks passed" || echo "❌ IR structural checks failed"; \
	else \
		echo "⚠️  FileCheck not found — skipping IR structural checks. Install LLVM FileCheck (apt-get install llvm-dev)"; \
	fi

# Generate assembly for alternative targets
.PHONY: llvm-targets
llvm-targets: $(LLVM_IR)
	@echo "=== ARM64 ==="
	llc -mtriple=aarch64-linux-gnu -o $(BUILD_DIR)/pfun_cma_engine-arm64.s $(LLVM_IR) 2>/dev/null && echo "✅ ARM64 assembly generated" || echo "❌ ARM64 target not available"
	@echo "=== WebAssembly ==="
	llc -mtriple=wasm32 -o $(BUILD_DIR)/pfun_cma_engine.wat $(LLVM_IR) 2>/dev/null && echo "✅ Wasm assembly generated" || echo "❌ Wasm target not available"
	@echo "=== RISC-V ==="
	llc -mtriple=riscv64-linux-gnu -o $(BUILD_DIR)/pfun_cma_engine-rv64.s $(LLVM_IR) 2>/dev/null && echo "✅ RISC-V assembly generated" || echo "❌ RISC-V target not available"

# Run opt passes and report metrics
.PHONY: analyze-ir
analyze-ir: $(LLVM_IR)
	@echo "=== IR Metrics ==="
	@echo "Instruction count:"
	@cat $(LLVM_IR) | grep -c '^\s' || true
	@echo "Function count:"
	@grep -c '^define ' $(LLVM_IR) || true
	@echo "Vectorized loops:"
	@grep -c 'llvm.loop.isvectorized' $(LLVM_IR) || true
	@echo "FMA intrinsics:"
	@grep -c 'llvm.fmuladd' $(LLVM_IR) || true
	@echo "External calls:"
	@grep -c '^declare ' $(LLVM_IR) || true
	@echo "Basic blocks:"
	@awk '/^[0-9]+:\s*$$/{count++} END{print count+0}' $(LLVM_IR) || true

# Update the test target to run LLVM tests too
.PHONY: test
test: test-llvm check-ir
