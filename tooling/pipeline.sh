#!/usr/bin/env bash
# pipeline.sh — launch the tool container from the host.
# Input and output paths are relative to the repository root, from any cwd.
#
# Usage (same arguments as run_pipeline.sh):
#   ./tooling/pipeline.sh vendor/design/rtl vendor/design/tb.v top [outputs/run]

set -euo pipefail

if [ "$#" -lt 3 ] || [ "$#" -gt 4 ]; then
    echo "Usage: pipeline.sh <design.v | design_folder> <testbench.v> <top_module> [output_dir]" >&2
    echo "All relative paths are resolved from the repository root." >&2
    exit 2
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"

exec docker run --rm \
    --volume "$REPO_ROOT:/workspace" \
    --workdir /workspace \
    rtlprobe-tools ./tooling/run_pipeline.sh "$@"
