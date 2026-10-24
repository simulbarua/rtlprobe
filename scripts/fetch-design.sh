#!/usr/bin/env bash
set -euo pipefail
data_root=${RTLPROBE_DATA_ROOT:?Set RTLPROBE_DATA_ROOT to the absolute experiment-data directory}
if [ "$#" -ne 1 ]; then
  echo 'Usage: fetch-design.sh /absolute/path/to/target.json' >&2
  exit 2
fi
script_dir=$(cd -- "$(dirname -- "$0")" && pwd)
exec "${RTLPROBE_PYTHON:-python3}" "$script_dir/rtlprobe.py" --data-root "$data_root" --target-config "$1" fetch
