#!/usr/bin/env bash
# pipeline.sh — run this ON YOUR MAC, not inside the container.
# It just wraps "docker run" so you only have to type one command.
#
# Usage (same arguments as run_pipeline.sh):
#   ./pipeline.sh picorv32.v testbench.v picorv32

set -euo pipefail
docker run --rm -v "$PWD":/workspace rtlprobe-tools ./run_pipeline.sh "$@"
