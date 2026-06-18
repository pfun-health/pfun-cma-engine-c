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

# Run tests (if available)
.PHONY: test
test:
	@echo "No tests configured yet"

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
	@echo "  help      - Show this help message"
