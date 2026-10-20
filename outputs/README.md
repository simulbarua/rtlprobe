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

The scripts under `tooling/` now default to this directory. The launcher resolves
all relative paths from the repository root; an explicit fourth argument can
choose another output directory. Historical `tooling/results/` evidence is
preserved in place. The current scripts do not yet implement all evidence and
validation policies described above.
