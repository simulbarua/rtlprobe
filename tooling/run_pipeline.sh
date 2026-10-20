#!/usr/bin/env bash
#
# run_pipeline.sh — RTLProbe tooling pipeline
#
# Runs Icarus Verilog, Verilator, and Yosys against one RTL design +
# testbench, and collects source, logs, AST, and synthesis output into
# a single results directory per run.
#
# Usage:
#   ./tooling/run_pipeline.sh <design.v | design_folder> <testbench.v> <top_module> [output_dir]
#
#   The design can be a single .v file (e.g. vendor/design/top.v) or a
#   folder, in which case every .v file in that folder is used
#   (e.g. vendor/design/rtl for a design split across several files).
#
# Meant to run from /workspace INSIDE the rtlprobe-tools container. From the
# repository root on the host:
#   ./tooling/pipeline.sh vendor/design/rtl vendor/design/tb.v top
# Relative paths (including firmware paths used by a bench) resolve from the
# repository root. Testbench-specific runtime preparation is still required.

set -uo pipefail

DESIGN="${1:?Usage: run_pipeline.sh <design.v> <testbench.v> <top_module> [output_dir]}"
TESTBENCH="${2:?Missing testbench file}"
TOP="${3:?Missing top module name}"

# Design files: one file as given, or every .v file in a folder.
if [ -d "$DESIGN" ]; then
    DESIGN_FILES=("$DESIGN"/*.v)
    if [ ! -f "${DESIGN_FILES[0]}" ]; then
        echo "No .v files found in folder $DESIGN"; exit 1
    fi
else
    DESIGN_FILES=("$DESIGN")
fi
echo "==> Design files: ${DESIGN_FILES[*]}"
TB_BASE="$(basename "$TESTBENCH" .v)"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
# Results folder: named after the top module (not the design path), so a
# folder like sha256/src/rtl doesn't produce a generic name such as "rtl".
OUTDIR="${4:-outputs/${TOP}__tb-${TB_BASE}__${TIMESTAMP}}"

mkdir -p "$OUTDIR"/{src,logs,ast,synth,coverage,waveform}

STATUS_FILE="$OUTDIR/status.txt"
: > "$STATUS_FILE"
record() { echo "$1: $2" >> "$STATUS_FILE"; }

echo "==> Collecting source"
cp "${DESIGN_FILES[@]}" "$TESTBENCH" "$OUTDIR/src/"

# --- 1. Compile with Icarus Verilog -----------------------------------
echo "==> Compiling with Icarus Verilog"
if iverilog -g2005 -o "$OUTDIR/sim.vvp" "${DESIGN_FILES[@]}" "$TESTBENCH" \
        > "$OUTDIR/logs/iverilog_compile.log" 2>&1; then
    record "iverilog_compile" "PASS"
else
    record "iverilog_compile" "FAIL"
fi

# --- 2. Run the simulation ---------------------------------------------
echo "==> Running simulation"
if [ -f "$OUTDIR/sim.vvp" ]; then
    # +vcd is PicoRV32's own convention (checked via $test$plusargs("vcd")
    # in its testbenches) for turning on waveform dumping. A different
    # dataset's testbench may not support this flag; if it doesn't, the
    # waveform step below just records NOT_PRODUCED rather than erroring.
    if timeout 120 vvp "$OUTDIR/sim.vvp" +vcd > "$OUTDIR/logs/sim.log" 2>&1; then
        record "simulation" "PASS"
    else
        # A design under test failing/hanging is itself useful data, not
        # a pipeline crash — record it but keep going.
        record "simulation" "FAIL_OR_TIMEOUT"
    fi
    # vvp writes the dump to ./testbench.vcd in the current directory
    # (this dataset's hardcoded filename, not something we control).
    if [ -f testbench.vcd ]; then
        mv testbench.vcd "$OUTDIR/waveform/wave.vcd"
        record "waveform" "PASS"
    else
        record "waveform" "NOT_PRODUCED"
    fi
else
    record "simulation" "SKIPPED (compile failed)"
    record "waveform" "SKIPPED (compile failed)"
fi

# --- 3. Verilator lint (structural sanity check) ------------------------
echo "==> Running Verilator lint"
if verilator --lint-only -Wall -Wno-fatal --top-module "$TOP" "${DESIGN_FILES[@]}" \
        > "$OUTDIR/logs/verilator_lint.log" 2>&1; then
    record "verilator_lint" "PASS"
else
    record "verilator_lint" "FAIL"
fi
# TODO: functional coverage collection needs Verilator's --coverage build
# flow (verilate + compile a C++ harness), which is a separate step from
# lint-only and depends on the testbench style. Not wired up yet — logging
# lint output for now as a placeholder for the coverage/ directory.
cp "$OUTDIR/logs/verilator_lint.log" "$OUTDIR/coverage/lint_signal.log" 2>/dev/null || true

# --- 4. Yosys: synthesis + AST + netlist ---------------------------------
echo "==> Running Yosys synthesis"
if yosys -p "
    read_verilog ${DESIGN_FILES[*]};
    hierarchy -top $TOP;
    proc; opt;
    synth -top $TOP;
    stat;
    write_json $OUTDIR/synth/netlist.json
" > "$OUTDIR/logs/yosys_synth.log" 2>&1; then
    record "yosys_synth" "PASS"
else
    record "yosys_synth" "FAIL"
fi

echo "==> Extracting AST (Yosys-native; see tooling/README.md#known-open-items)"
# Default choice pending a final decision with Dipti on AST format; this
# is the lowest-friction option since Yosys is already in the toolchain.
# Swap this block for Verible or Pyverilog output here if the team decides
# to go that way instead — nothing else in the script depends on this format.
if yosys -p "read_verilog -dump_ast2 ${DESIGN_FILES[*]}" \
        > "$OUTDIR/ast/ast_dump.txt" 2>&1; then
    record "ast_dump" "PASS"
else
    record "ast_dump" "FAIL"
fi

# --- Summary -------------------------------------------------------------
echo ""
echo "==> Done. Results in: $OUTDIR"
echo "----- status.txt -----"
cat "$STATUS_FILE"
