# RTL target configurations

Create one subdirectory for each selected target/configuration. A repository may
provide several independently configured targets.

Each target directory should contain a README with its scope and reproduction
instructions, a machine-readable configuration once its schema is implemented,
and any required file lists or small integration adapters/patches.

Record the upstream URL and immutable revision, ordered HDL inputs, design and
simulation tops, include paths, defines, parameters, dependencies, existing tests,
runtime inputs, checker interpretation, tool requirements, and execution limits.
Use repository-relative paths with documented resolution rules.

Existing Makefiles, FuseSoC files, and scripts are sources of build information.
Their presence alone does not qualify a target. Dataset admission requires an
existing usable testbench/checker, an executed baseline PASS, and demonstrated
checker sensitivity. Defer or exclude targets without a usable existing checker.

Keep downloaded sources in `vendor/` and measured qualification evidence in
`outputs/`. This scaffold adds no configurations and no configuration loader.
