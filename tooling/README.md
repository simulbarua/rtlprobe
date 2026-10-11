# RTLProbe Tooling Pipeline

Containerized environment plus automation script for compiling, simulating,
linting, and synthesizing RTL designs with a pinned, reproducible toolchain.
Built for the RTLProbe capstone project's dataset/tooling workstream.

## Prerequisites

- Docker Desktop installed and running (Mac, Windows/WSL2, or Linux all work
  identically once the image is built, that's the whole point of using
  Docker here)

## One-time setup

From the folder containing `Dockerfile`, `run_pipeline.sh`, and
`pipeline.sh`:

```
docker build -t rtlprobe-tools .
```

First build takes several minutes since it compiles Verilator from source.
Only rebuild this when the Dockerfile itself changes (a tool version
changes); rebuilding is not needed when you just edit `run_pipeline.sh`.

## Running the pipeline

**Your RTL design and testbench files must be in the same folder as
`run_pipeline.sh` and `pipeline.sh`** (or a subfolder underneath, referenced
by relative path). The container only sees whatever folder you're standing
in when you run it.

```
./pipeline.sh <design.v> <testbench.v> <top_module_name>
```

Example, if your files are in a `picorv32/` subfolder:

```
./pipeline.sh picorv32/picorv32.v picorv32/testbench_ez.v picorv32
```

`pipeline.sh` is a thin convenience wrapper around:

```
docker run --rm -v "$PWD":/workspace rtlprobe-tools ./run_pipeline.sh <args>
```

Either form works, `pipeline.sh` just saves typing.

## What it does

1. Copies your source files into the results folder (a snapshot of exactly
   what produced this run's results)
2. Compiles and simulates with Icarus Verilog (120s timeout, so a hung
   simulation can't stall the run)
3. Runs Verilator in lint-only mode (static check, no simulation)
4. Runs Yosys: full synthesis (dumps a netlist as JSON) plus a separate AST
   dump

## Output

Results land in
`results/<design>__tb-<testbench>__top-<top_module>__<timestamp>/` inside
the same folder you ran the command from (not lost when the container
exits, `--rm` only removes the container, not the mounted files). The
folder name itself tells you which design, testbench, and top module
produced it, e.g.:

```
results/picorv32__tb-testbench_ez__top-picorv32__20260923_015926/
├── status.txt        ← PASS / FAIL / SKIPPED per stage
├── src/               ← copy of the RTL + testbench used
├── logs/               ← one log per tool
├── ast/ast_dump.txt   ← Yosys AST dump
├── synth/netlist.json ← synthesized netlist
└── coverage/          ← placeholder, not wired up yet (see below)
```

Each run gets its own folder, so running the same design against
different testbenches, or the same combination twice, never overwrites
a previous result.

You can override the folder name entirely with a 4th argument:
`./pipeline.sh design.v testbench.v top_module my_custom_name`.

## Testbenches confirmed working (PicoRV32)

- **`testbench_ez.v`** (top module `picorv32`) — runs a full simulation to
  completion, no firmware image needed. Best one to use as a quick smoke
  test.
- **`testbench.v`** (top module `picorv32`) — compiles fine, but needs a
  compiled `firmware/firmware.hex` to actually simulate; without it,
  `simulation` will show `FAIL_OR_TIMEOUT`.
- **`testbench_wb.v`** (different top module: `picorv32_wb`) — compiles
  fine, also needs a firmware image to simulate.

All three, plus the design file itself, have been confirmed to pass
Icarus, Verilator, and Yosys end to end on an actual team machine (not
just in testing).

## Pinned tool versions

| Tool           | Version | Source                       |
|----------------|---------|-------------------------------|
| Icarus Verilog | 12.0    | apt (exact match on Ubuntu 24.04) |
| Yosys          | 0.33    | apt                            |
| Verilator      | 5.038   | built from source (git tag `v5.038`) |
| Python         | 3.12.3  | apt (Ubuntu 24.04 default)     |

Full rationale in `VERSIONS.md`.

## Known open items

- **AST library**: currently defaults to Yosys's own AST dump
  (`read_verilog -dump_ast2`), a plain-text format. This is a placeholder
  pending a decision with Dipti on what format her model actually needs
  (Verible's JSON output and Pyverilog are the other candidates under
  consideration). Swapping this later is a self-contained change, nothing
  else in the script depends on the AST format.
- **Coverage collection**: not implemented yet. The `coverage/` folder
  currently just gets a copy of the Verilator lint log as a placeholder.
  Real functional coverage needs Verilator's separate `--coverage` build
  flow (compiling a C++ harness), which depends on how each testbench is
  structured.

## Troubleshooting

**`stat ./run_pipeline.sh: no such file or directory`** — you're not
standing in the folder the script is actually in. Run `pwd` and `ls` to
check, then `cd` to the right folder, or `mv` the script there.

**`cp: cannot stat 'design.v': No such file or directory`** — same idea,
but for your RTL files specifically. If they're in a subfolder, include
that subfolder in the path you pass to the script (e.g.
`picorv32/picorv32.v`, not just `picorv32.v`).

**`zsh: permission denied: ./pipeline.sh`** — the executable bit didn't
carry over (common after downloading a fresh copy of the script). Run
`chmod +x pipeline.sh run_pipeline.sh` once and try again.

**Verilator warnings that end in `%Error: Exiting due to N warning(s)`**
— this is Verilator's own policy of treating lint warnings as fatal by
default. `run_pipeline.sh` already passes `-Wno-fatal` to prevent a
stylistically imperfect (but otherwise fine) design from being wrongly
logged as FAIL. If you ever run Verilator manually without that flag,
don't be alarmed by a wall of warnings on real RTL, most are style
nitpicks, not actual bugs.
