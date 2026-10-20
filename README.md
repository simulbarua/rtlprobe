# RTLProbe

**RTLProbe: Multimodal Machine Learning for RTL Debugging and Bug Localization**

RTLProbe is a research project focused on applying multimodal machine learning to hardware debugging. The project aims to combine information from RTL source code, design structure, verification results, and synthesized netlists to identify and localize hardware design bugs.

## Status

Project under development.

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

Each directory has a README describing its purpose. The implementation, target,
and test directories currently provide an organizational scaffold; this change
does not implement the proposed generic pipeline or import the separate local
workarea. Python package metadata will be added with the package implementation.

The Dockerfile is at the repository root. Build the image from that directory:

```sh
docker build -t rtlprobe-tools .
```

Both pipeline scripts remain under `tooling/`. The launcher mounts the repository
root at `/workspace` and sets that as the container's working directory. All
relative input/output paths are repository-relative, regardless of the host's
current directory. Runs default to `outputs/`; downloaded sources belong in
`vendor/`. See the [tooling instructions](tooling/README.md) for examples.

The root `.dockerignore` excludes downloaded sources, generated evidence, local
environments, and Git metadata from image builds. These exclusions do not affect
the repository bind mount used when running the pipeline.

Agent implementations, model prompts, and provider integrations belong in a
separate repository. RTLProbe's execution and research implementation should be
usable through ordinary configuration files and commands.
