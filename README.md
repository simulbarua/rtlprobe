# RTLProbe

**RTLProbe: Multimodal Machine Learning for RTL Debugging and Bug Localization**

RTLProbe is a research project focused on applying multimodal machine learning to hardware debugging. The project aims to combine information from RTL source code, design structure, verification results, and synthesized netlists to identify and localize hardware design bugs.

## Status

Project under development.

Candidate repositories are listed in the [repository catalog spreadsheet](docs/RTLProbe_Repository_Catalog.xlsx).
See its [provenance and qualification limits](docs/README.md#repository-catalog).

## Repository structure

```text
rtlprobe/
├── README.md
├── .gitignore
├── .dockerignore   Docker build-context exclusions
├── Dockerfile      Hardware-tool environment
├── rtlprobe/       Python pipeline and research implementation
├── targets/        RTL target configurations and reproduction instructions
├── tests/          Tests of RTLProbe software
├── experiments/    Localization experiments and training baselines
├── docs/           Technical and research documentation
├── meetings/       Team and advisor meeting notes
├── scripts/        Setup and maintenance helpers
├── vendor/         Downloaded upstream repositories (contents ignored)
├── data/           Dataset records and metadata
├── outputs/        Generated execution evidence (contents ignored)
└── tooling/        Existing pipeline scripts and tooling notes
```

The runner qualifies targets, executes reviewed mutations, and verifies evidence.
Select a target manifest and an external experiment data root using the
[runner command-line interface](docs/execution-layout.md). See the
[training pipeline](experiments/training/README.md) for model training, dataset
splits, and evaluation.
Human acceptance, automatic promotion, sampling, and separate acceptance counts are documented in [case curation](docs/execution-layout.md#case-curation).
The SHA-256 and ChaCha targets have real pilot evidence. Other targets need a compatible manifest,
existing testbench, trusted checker adapter, and fresh qualification. The backend is
currently Icarus/Verilator/Yosys with five approved mutation operators; this is
not arbitrary-repository automation or a trained localizer.

### Which toolchain is authoritative

Every accepted case was qualified and executed with the native Mac toolchain
recorded in each sealed qualification fingerprint: Icarus Verilog 13.0,
Verilator 5.046, Yosys 0.69. Since October 23, 2026 the
root `Dockerfile` builds those same three versions from their upstream tags
(`v13_0`, `v5.046`, `v0.69`), replacing the earlier image pins (Icarus 12.0,
Yosys 0.33, Verilator 5.038) that had produced none of the accepted evidence.
The image was built and smoke-tested on that date on linux/arm64 (Colima on the
development Mac): the three version banners, an Icarus simulation, a Verilator
lint, and a Yosys synthesis of a small counter all passed; the versions the
image reports are recorded inside it at `/etc/rtlprobe-toolchain-versions.txt`.

Identical versions do not mean an identical environment fingerprint: the
runner hashes each tool's full version banner, which includes the compiler and
git sha, and the Mac's Yosys is a Homebrew build one merge commit past the tag
(`0.69+post`). A new host or the image must therefore run
`scripts/rtlprobe.py qualify` for each target before producing cases. The
`tooling/` pipeline remains the historical raw-artifact workflow.

The Dockerfile is at the repository root. Build the image from that directory:

```sh
docker build -t rtlprobe-tools .
```

Both pipeline scripts remain under `tooling/`. The launcher mounts the repository
root at `/workspace` and sets that as the container's working directory. All
relative input/output paths for that tooling launcher are repository-relative,
regardless of the host's current directory. Those runs default to `outputs/`;
downloaded sources belong in `vendor/`. The Python mutation runner instead uses
an explicit external data root. See the [tooling instructions](tooling/README.md) for examples.

The root `.dockerignore` excludes downloaded sources, generated evidence, local
environments, and Git metadata from image builds. These exclusions do not affect
the repository bind mount used when running the pipeline.

## Execution backends

Target manifests select `backend: icarus` (the default), `verilator_predv`, or
`verilator_uvm`. Existing SHA-256 and ChaCha manifests and checker adapters are
unchanged. Both Verilator variants bind each fresh build to the exact source
hashes and refuse execution after a source or binary change.

OpenTitan targets currently support **original-only proof**, with each control
recorded as `pending: front end`. `qualify` runs every admitted test, saves an
`original-proof.json` and sealed manifest, and never writes a qualified design
dossier. These proofs do not enable case generation. Control/restored-PASS,
structural admission, specification stores, and host qualification remain gates.

See [backend operation](docs/verilator-backends.md) for pinned tools, reproduction,
checker contracts, and qualification requirements.

## Mutation operators and candidate syntax

Mutation mapping uses pinned pyslang for Verilog and SystemVerilog. The five
[registry operators](rtlprobe/operators.json) are approved; target qualification,
site applicability, study candidate-rule adoption and case acceptance remain
separate gates. Source-only candidate extraction does not establish dependency
or waveform mapping coverage.

See [mutation operators](docs/mutation-operators.md) for constraints and read-only
inspection commands, and [localization](docs/localization.md) for the experimental
graph/trace pipeline and its limits.

## Documentation

The [documentation index](docs/README.md) links the runner guides, dataset
formats, reproduction instructions, and capstone experiments.
