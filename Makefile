# Use bash for all shell commands
SHELL := /bin/bash

# Variables
PYTHON := python3
VENV_DIR := .venv
VENV_PYTHON := $(VENV_DIR)/bin/python
C_SOURCE := launcher.c
BUILD_DIR := build
EXECUTABLE := $(BUILD_DIR)/launcher

# Default target: build the C launcher
all: $(EXECUTABLE)

# Build the C launcher executable
$(EXECUTABLE): $(C_SOURCE) $(BUILD_DIR)
	gcc -O2 -s -o $(EXECUTABLE) $(C_SOURCE)

# Create the build directory
$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

# Setup the Python virtual environment and install dependencies
setup:
	uv venv
	uv pip install -e .

# Update Python Packages
update:
	uv pip compile requirements.txt -o requirements.txt

# Run the launcher for development
run: all
	./$(EXECUTABLE)

# Clean up build artifacts and virtual environment
clean:
	rm -rf $(BUILD_DIR)
	rm -rf $(VENV_DIR)
	rm -rf launcher.egg-info
	find . -type d -name "__pycache__" -exec rm -r {} +

# Compile all python files to bytecode for faster startup
compile:
	$(VENV_PYTHON) -m compileall .

# Lint and format Python code
lint:
	ruff check --select I --fix
	ruff format

.PHONY: all setup update run clean compile lint
