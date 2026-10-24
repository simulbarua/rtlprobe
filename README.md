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
├── docs/           Technical and research documentation
├── meetings/       Team and advisor meeting notes
├── scripts/        Setup and maintenance helpers
├── vendor/         Downloaded upstream repositories (contents ignored)
├── data/           Dataset records and metadata
├── outputs/        Generated execution evidence (contents ignored)
└── tooling/        Existing pipeline scripts and tooling notes
```

The deterministic qualification/mutation runner uses an explicitly selected target
manifest, with no default repository or two-repository allowlist. The main repository owns its scripts, contracts, operators,
checker, and evidence handling. Agent skills, model prompts, and orchestration live
in the separate `rtlprobe-agents` repository. Experiment data lives at an explicitly
configured external root. See [execution layout and script interface](docs/execution-layout.md).
The SHA-256 and ChaCha targets have real pilot evidence. Other targets need a compatible manifest,
existing testbench, trusted checker adapter, and fresh qualification. The backend is
currently Icarus/Verilator/Yosys with two narrow 32-bit mutation operators; this is
not arbitrary-repository automation or a trained localizer.

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

Agent implementations, model prompts, and provider integrations belong in a
separate repository. RTLProbe's execution and research implementation should be
usable through ordinary configuration files and commands.
