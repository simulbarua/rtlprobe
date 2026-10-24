# RTLProbe Tooling Pipeline

> Historical tooling workstream. Since 2026-10-23 the image pins the same tool versions as the native toolchain that produced every accepted case; see the root README, "Which toolchain is authoritative". The image's version banners still differ from the Mac's, so it never reproduces the Mac fingerprint.

Containerized environment plus automation script for compiling, simulating,
linting, and synthesizing RTL designs with a pinned, reproducible toolchain.
Built for the RTLProbe capstone project's dataset/tooling workstream.

## Prerequisites

- Docker Desktop installed and running (Mac, Windows/WSL2, or Linux all work
  identically once the image is built, that's the whole point of using
  Docker here)

## One-time setup

The Dockerfile is at the repository root; both pipeline scripts remain in
`tooling/`. From the repository root, build the image:

```
docker build -t rtlprobe-tools .
```

If your shell is already in `tooling/`, the equivalent build command is:

```sh
docker build -f ../Dockerfile -t rtlprobe-tools ..
```

First build takes a long time since it compiles Icarus, Verilator, and Yosys from source.
Only rebuild this when the Dockerfile itself changes (a tool version
changes); rebuilding is not needed when you just edit `run_pipeline.sh`.

## Running the pipeline

From the repository root:

```sh
./tooling/pipeline.sh <design.v-or-folder> <testbench.v> <design_top> [output_dir]
```

The launcher locates the repository from its own path, mounts the entire root at
`/workspace`, and explicitly runs there. **Relative paths always refer to the
repository root**, even when you invoke the launcher from `tooling/` or another
directory. Keep inputs within the mounted repository; host absolute paths outside
it are not available inside the container.

For example, with a checkout under `vendor/picorv32/`:

```sh
./tooling/pipeline.sh vendor/picorv32/picorv32.v vendor/picorv32/testbench_ez.v picorv32
```

From `tooling/`, the same inputs are still repository-relative:

```sh
./pipeline.sh vendor/picorv32/picorv32.v vendor/picorv32/testbench_ez.v picorv32
```

The equivalent direct Docker command, run from the repository root, is:

```sh
docker run --rm -v "$PWD":/workspace -w /workspace rtlprobe-tools ./tooling/run_pipeline.sh <args>
```

The root `.dockerignore` keeps local environments, Git metadata, downloaded RTL,
and generated results out of the image build context. Runtime bind mounts still
expose `vendor/`, `targets/`, and `outputs/`. Rebuild from the repository root (or
use the `..` context above) so this ignore policy is applied consistently.

Simulation also runs from the repository root. A testbench that opens relative
firmware or memory paths still needs those runtime inputs prepared at its expected
location; this launcher change does not resolve testbench dependencies.

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
`outputs/<top_module>__tb-<testbench>__<timestamp>/` under the repository root.
Results survive container removal because the repository is bind-mounted. The
folder name identifies the design top and testbench, e.g.:

```
outputs/picorv32__tb-testbench_ez__<timestamp>/
├── status.txt        ← PASS / FAIL / SKIPPED per stage
├── src/               ← copy of the RTL + testbench used
├── logs/               ← one log per tool
├── ast/ast_dump.txt   ← Yosys AST dump
├── synth/netlist.json ← synthesized netlist
└── coverage/          ← placeholder, not wired up yet (see below)
```

The default name includes a timestamp with one-second resolution. Use distinct
explicit output directories for runs started in the same second, and do not reuse
an existing output directory. Collision protection remains future work.

You can override the folder name entirely with a 4th argument:
`./tooling/pipeline.sh design.v testbench.v top_module outputs/my_custom_name`.
Relative overrides are also resolved from the repository root. Historical
`tooling/results/` evidence is left in place.

## Testbenches confirmed working (PicoRV32)

- **`testbench_ez.v`** (top module `picorv32`) — runs a full simulation to
  completion, no firmware image needed. Best one to use as a quick smoke
  test.
- **`testbench.v`** (top module `picorv32`) — compiles fine, but needs a
  compiled `firmware/firmware.hex` to actually simulate; without it,
  `simulation` will show `FAIL_OR_TIMEOUT`.
- **`testbench_wb.v`** (different top module: `picorv32_wb`) — compiles
  fine, also needs a firmware image to simulate.

These are historical team-machine observations, not fresh validation of this
launcher or environment. See [datasets tried](DATASETS.md) and
[pipeline findings](FINDINGS.md) for the observed limitations, including missing
firmware and the difference between simulation completion and functional PASS.

## Toolchain declarations

| Tool           | Version | Source                       |
|----------------|---------|-------------------------------|
| Icarus Verilog | 13.0    | built from source (git tag `v13_0`) |
| Yosys          | 0.69    | built from source (git tag `v0.69`, CMake) |
| Verilator      | 5.046   | built from source (git tag `v5.046`) |
| Python         | Not explicitly pinned | Ubuntu apt package `python3` |

The [root Dockerfile](../Dockerfile) is the source of these declarations. The
Ubuntu base tag and remaining apt dependencies are not locked by digest or a
package snapshot. Record the actual image identity, architecture, and tool
versions for experiments; these declarations alone are not a fresh build result.

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

**`stat ./run_pipeline.sh: no such file or directory`** — an old direct Docker
command may be using the previous script path. Mount the root, set `-w /workspace`,
and invoke `./tooling/run_pipeline.sh`, or use the launcher shown above.

**`cp: cannot stat 'design.v': No such file or directory`** — same idea,
but for your RTL files specifically. Supply repository-relative paths, such as
`vendor/picorv32/picorv32.v`, regardless of the directory you launch from.

**`zsh: permission denied: ./pipeline.sh`** — the executable bit didn't
carry over (common after downloading a fresh copy of the script). Run
`chmod +x tooling/pipeline.sh tooling/run_pipeline.sh` from the repository root
once and try again.

**Verilator warnings that end in `%Error: Exiting due to N warning(s)`**
— this is Verilator's own policy of treating lint warnings as fatal by
default. `run_pipeline.sh` already passes `-Wno-fatal` to prevent a
stylistically imperfect (but otherwise fine) design from being wrongly
logged as FAIL. If you ever run Verilator manually without that flag,
don't be alarmed by a wall of warnings on real RTL, most are style
nitpicks, not actual bugs.

## Verilator execution support (October 24, 2026)

`verilator-uvm/` is current execution support, distinct from historical tooling.
It contains the original Accellera 1800.2-2017-1.0 distribution (Apache-2.0,
LICENSE and NOTICE retained), the compatibility macro, and hash-checked unified
diffs. It contains no OpenTitan source tree.

The Mac uses Homebrew Verilator 5.046 for pre_dv and the trial's separate
`prefix/bin/verilator` at `0041d207c3dcede92f48b86e0c7e2b70626cd86c` for UVM.
Source the trial's `work/env.sh` to select Homebrew LLVM and SDKROOT. Set
`RTLPROBE_VERILATOR_PREDV`, `RTLPROBE_VERILATOR_UVM`,
`RTLPROBE_VERILATOR_UVM_SOURCE`, and `RTLPROBE_FUSESOC`; see
[the backend guide](../docs/verilator-backends.md). The trial directories are
read-only references. Builds, patches and generated caches go into new run roots.
