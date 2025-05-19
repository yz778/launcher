#!/bin/bash

# Create a virtual environment
python3 -m venv .venv

# Activate the virtual environment
source .venv/bin/activate

# Install the launcher in development mode
# This will automatically install all dependencies from requirements.txt via setup.py
uv pip install -e .

echo "Virtual environment set up successfully in .venv!"
echo "To run the launcher, run: ./launcher.sh"
