#!/bin/sh

set -e

cd "$(dirname "$(readlink -f "$0")")"
.venv/bin/python main.py "$@"
