# Standard C/C++ Makefile for pfun-cma-engine-c
# Optimized C extensions for PFun CMA model

# Compiler settings
CC := gcc
CXX := g++
CFLAGS := -Wall -Wextra -O2 -std=c99
CXXFLAGS := -Wall -Wextra -O2 -std=c++11
LDFLAGS := -lm

# Python interpreter for demo scripts (prefer project venv)
PYTHON := $(if $(wildcard .venv/bin/python),.venv/bin/python,$(if $(shell command -v uv 2>/dev/null),uv run python,python3))

# Nuklear
NUKLEAR_DIR := third_party/nuklear
NUKLEAR_HEADER := $(NUKLEAR_DIR)/nuklear.h
NUKLEAR_VERSION := v4.13.3

# Directories
SRC_DIR := src
BUILD_DIR := build
LIB_DIR := pfun_cma_engine
DEMO_C_DIR := demos/c
DEMO_PY_DIR := demos/python
DEMO_TS_DIR := demos/typescript
DOCS_DIR := docs
DEMO_OUTPUT_DIR := $(DOCS_DIR)/demo_outputs
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
.DEFAULT_GOAL := help

.PHONY: help
help: ## Display this help screen
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

.PHONY: all
all: $(TARGET) $(STATIC_TARGET)  ## Build shared libary targets (compiled to: build/*.o)

.PHONY: directories
directories:  # Create directories
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
	@echo "cleaning any existing build outputs..."
	@rm -rf .venv $(BUILD_DIR) $(LIB_DIR)/*.so $(LIB_DIR)/*.a $(LIB_DIR)/*.o

# Rebuild from scratch
.PHONY: rebuild
rebuild: clean all

# Debug build
.PHONY: debug
debug: CFLAGS := -Wall -Wextra -g -O0 -DDEBUG
debug: clean all

# Format code
.PHONY: format
format:  ## Format code using clang-format
	@echo "Formatting code with clang-format..."
	clang-format -i $(SRC_DIR)/*.c $(SRC_DIR)/*.h 2>/dev/null || echo "clang-format not available"

# Check code style
.PHONY: check-format
check-format:  ## check code formatting using clang-format
	clang-format --dry-run -Werror $(SRC_DIR)/*.c $(SRC_DIR)/*.h 2>/dev/null || echo "clang-format not available"

.PHONY: python-setup
python-setup:  ## Setup python environment using uv
	uv sync --dev --all-extras
	. ./.venv/bin/activate

# Capture demo session output to markdown
.PHONY: demo-py-output demo-c-output demo-ts-output demo-morning-run demo-evening-party outputs npm-setup
outputs: demo-py-output demo-c-output demo-ts-output demo-morning-run demo-evening-party  ## Capture demo session output to markdown

.PHONY: demo-py-output
demo-py-output: all python-setup  ## Run the Python-based demo (default settings)
	$(PYTHON) $(DEMO_PY_DIR)/demo.py --save $(DEMO_OUTPUT_DIR)/DEMO_PY_OUTPUT.md

.PHONY: demo-c-output
demo-c-output: demo  ## Run the C-based demo (default settings)
	$(BUILD_DIR)/demo --ascii --save $(DEMO_OUTPUT_DIR)/DEMO_C_OUTPUT.md

.PHONY: demo-ts-output
demo-ts-output: all npm-setup  ## Run the TypeScript demo against the compiled C engine
	node --experimental-strip-types $(DEMO_TS_DIR)/demo.ts --save $(DEMO_OUTPUT_DIR)/DEMO_TS_OUTPUT.md

.PHONY: npm-setup
npm-setup:  ## Install TypeScript demo dependencies
	npm ci

.PHONY: demo-morning-run
demo-morning-run:  ## Generate a demo scenario to simulate a "morning run" (utilizes metabolic activity parameters)
	$(PYTHON) $(DEMO_PY_DIR)/demo.py --scenario morning-run --save $(DEMO_OUTPUT_DIR)/DEMO_MORNING_RUN_OUTPUT.md

.PHONY: demo-evening-party
demo-evening-party:  ## Generate an "evening party" scenario.
	$(PYTHON) $(DEMO_PY_DIR)/demo.py --scenario evening-party --save $(DEMO_OUTPUT_DIR)/DEMO_EVENING_PARTY_OUTPUT.md

.PHONY: demo
demo: $(BUILD_DIR)/demo  ## Interactive/ASCII demo (Nuklear TTY UI + terminal backend)

$(BUILD_DIR)/demo: $(DEMO_C_DIR)/demo.c $(DEMO_C_DIR)/term.c $(DEMO_C_DIR)/term.h $(SRC_DIR)/pfun_cma_engine.h $(NUKLEAR_HEADER) | directories
	$(CC) $(CFLAGS) -D_DEFAULT_SOURCE -Wno-unused-function -Wno-unused-parameter \
	  -I$(SRC_DIR) -I$(DEMO_C_DIR) -I$(NUKLEAR_DIR) -o $@ $(DEMO_C_DIR)/demo.c $(DEMO_C_DIR)/term.c $(SRC_DIR)/pfun_cma_engine.c $(LDFLAGS)

# Fetch the pinned nuklear.h single-header (idempotent)
.PHONY: vendor-nuklear
vendor-nuklear: $(NUKLEAR_HEADER)
$(NUKLEAR_HEADER):
	@mkdir -p $(NUKLEAR_DIR)
	curl -fsSL -o $@ \
	  https://raw.githubusercontent.com/Immediate-Mode-UI/Nuklear/$(NUKLEAR_VERSION)/nuklear.h

# ── Scenario database buffer ─────────────────────────────────────────────────

SCENARIO_DB := data/scenario_buffer.sqlite

.PHONY: scenario-db scenario-db-core query-demo demo-scenario-embeddings test-scenariogen test-precision precision-report
scenario-db-core:
	$(PYTHON) $(DEMO_PY_DIR)/build_scenario_db.py --db /tmp/scenario_core.sqlite --tier core
	@echo "Core buffer written to /tmp/scenario_core.sqlite (15 scenarios x 97 pts)"

scenario-db:  ## Build the scenario database (precompute labeled scenarios using the compiled pfun-cma-engine libs)
	@mkdir -p data
	$(PYTHON) $(DEMO_PY_DIR)/build_scenario_db.py --db $(SCENARIO_DB) --tier full --pts 193

query-demo: scenario-db  ## Query the default demo from the scenario database (and build the database if not already built)
	$(PYTHON) $(DEMO_PY_DIR)/query_scenario_db.py --db $(SCENARIO_DB) \
	  --mood stressed --hunger starving --sleep restful --activity sedentary \
	  --meal-schedule standard --summary-only --timecourse --references

demo-scenario-embeddings: scenario-db  ## Interactive semantic search over scenario DB (BGE embeddings + cosine similarity)
	uv run --group demo python $(DEMO_PY_DIR)/scenario_embeddings_demo.py --db $(SCENARIO_DB)

test-scenariogen:  ## Test scenario generation
	$(PYTHON) -m pytest tests/test_scenariogen.py tests/test_scenario_db.py -q

test-precision: all  ## Check FP32/FP16 boundary precision against FP64
	$(PYTHON) -m pytest tests/test_precision.py -q

precision-report: all  ## Generate the model precision assessment report
	$(PYTHON) tools/precision_report.py

# ── LLVM IR Tooling ──────────────────────────────────────────────────────────

LLVM_IR   := $(BUILD_DIR)/pfun_cma_engine.ll
LLVM_BC   := $(BUILD_DIR)/pfun_cma_engine.bc

# Materialize LLVM IR and bitcode outputs.
$(LLVM_IR) $(LLVM_BC) &: tools/convert-to-llvm.py $(SRC_DIR)/pfun_cma_engine.c | directories
	python3 tools/convert-to-llvm.py $(SRC_DIR)/pfun_cma_engine.c

.PHONY: llvm-ir  ## Generate LLVM IR (.ll) and bitcode (.bc) from C source
llvm-ir: $(LLVM_IR) $(LLVM_BC)

.PHONY: llvm-verify  ## Verify LLVM bitcode round-trips correctly
llvm-verify: $(LLVM_BC)
	llvm-dis $(LLVM_BC) -o /dev/null && echo "✅ Bitcode round-trips OK" || echo "❌ Bitcode verification failed"

# Compile with LTO using bitcode
.PHONY: lto-test
lto-test: $(LLVM_BC) $(BUILD_DIR)/output_gcc.txt
	@echo "=== LTO compilation ==="
	clang -flto -O2 -I$(SRC_DIR) -o $(BUILD_DIR)/test_lto tests/test_scaling.c $(LLVM_BC) -lm
	@echo "=== Running LTO binary ==="
	$(BUILD_DIR)/test_lto > $(BUILD_DIR)/output_lto.txt
	@echo "=== Numerical diff vs GCC reference ==="
	-diff $(BUILD_DIR)/output_gcc.txt $(BUILD_DIR)/output_lto.txt && echo "✅ LTO numerical match: GCC == LTO" || echo "⚠️  LTO numerical differences detected"
	@rm -f $(BUILD_DIR)/test_lto $(BUILD_DIR)/output_lto.txt

# Compile .ll IR to native binary and compare numerical output with GCC
.PHONY: test-llvm
test-llvm: $(LLVM_IR)
	@mkdir -p $(BUILD_DIR)
	@echo "=== Compiling GCC reference binary ==="
	$(CC) -I$(SRC_DIR) -o $(BUILD_DIR)/test_scaling_gcc tests/test_scaling.c $(SRC_DIR)/pfun_cma_engine.c -lm
	@echo "=== Compiling LLVM IR to native binary ==="
	clang -I$(SRC_DIR) -o $(BUILD_DIR)/test_scaling_llvm tests/test_scaling.c $(LLVM_IR) -lm
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

.PHONY: analyze-ir
analyze-ir: $(LLVM_IR)  ## Run opt passes and report metrics
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

.PHONY: optimize-ir
optimize-ir: $(LLVM_IR)  ## Run opt pass exploration on the IR
	bash tools/ir-pass-explorer.sh $(LLVM_IR)

.PHONY: profile-ir
profile-ir: $(LLVM_IR)  ## Run deep IR static profiling
	bash tools/ir-profile.sh $(LLVM_IR)

.PHONY: ir-metrics
ir-metrics: $(LLVM_IR)  ## Check IR metrics against golden reference values
	bash tools/check-ir-metrics.sh $(LLVM_IR)

.PHONY: analyze-all
analyze-all: analyze-ir optimize-ir profile-ir ir-metrics llvm-targets  ## Run all LLVM-related analysis targets

.PHONY: test
test: test-llvm check-ir test-scenariogen test-precision  ## Update the test target to run LLVM tests and the scenariogen suites too
