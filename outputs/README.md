# Generated execution evidence

Use unique per-target/per-run directories for captured input snapshots, effective
configuration, commands, tool/environment identity, build artifacts, logs,
waveforms, coverage, ASTs, synthesized netlists, timing, and artifact manifests.
Preserve source-relative paths inside snapshots.

Git ignores this directory's contents except this README. Ignored evidence still
needs retention and backups when experiment records depend on it. Preserve sealed
bundles and record fresh execution separately from historical evidence reuse.

Mark unsupported or uncollected modalities explicitly. Lint logs are not coverage,
and simulator completion alone is not a functional PASS.

This is the destination for future integrated execution. The unchanged scripts
under `tooling/` still write to their existing `results/` location unless an
explicit output argument is supplied.
