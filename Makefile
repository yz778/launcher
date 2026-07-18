# Use bash for all shell commands
SHELL := /bin/bash

# Variables
PYTHON := python3
VENV_DIR := .venv
VENV_PYTHON := $(VENV_DIR)/bin/python

# Setup the Python virtual environment and install dependencies
setup:
	uv venv
	uv pip install -e .

# Run the launcher for development
run:
	$(VENV_PYTHON) -m launcher

# Clean up build artifacts and virtual environment
clean:
	rm -rf build/
	rm -rf dist/
	rm -rf launcher.egg-info
	find . -type d -name "__pycache__" -exec rm -r {} +

# Compile all python files to bytecode for faster startup
compile:
	$(VENV_PYTHON) -m compileall .

# Lint and format Python code
lint:
	uvx ruff check --select I --fix || exit 1
	uvx ruff format

.PHONY: setup run clean compile lint
