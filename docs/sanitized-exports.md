# Sanitized localization exports

`rtlprobe.sanitized_export` creates one write-once, read-only evidence directory
per condition from an audited buggy-evidence companion bundle. It does not run
simulations or a localizer, accept defects, supply a study protocol decision, or
release a project execution hold. The current evidence-capture implementation
and supported constructs determine which inputs can be exported completely.

The command accepts an external curator root, a neutral sample identifier and
common context. For example, using paths chosen for your external data layout:

```sh
python -m rtlprobe.sanitized_export \
  --bundle /data/curator/capture \
  --common-context /data/curator/common-context.json \
  --curator-root /data/curator \
  --output /data/inference/sample-0123456789abcdef/C0 \
  --condition C0 --neutral-id sample-0123456789abcdef \
  --provenance-output /data/curator/export-receipts/sample-0123456789abcdef-C0.json
```

The output must be outside source repositories and the curator root. Existing
outputs and receipts are never overwritten. The trusted receipt is kept outside
inference inputs; it binds the export manifest to the input evidence manifest
and, where applicable, the independently frozen specification store.

## Common context

`common-context.json` has exactly `configuration`, `sources`, `logs` and
`hierarchy`. It contains observed buggy-run material, not curator annotations.

The configuration projects only `top`, `test_top`, `test_id`, `rtl`,
`testbench`, `defines`, `parameters` and `seed`. A full target manifest may be
supplied at this input boundary, but all other configuration fields are
withheld. In particular, control edits, vendor paths, qualification pointers,
budgets, dossier notes and the legacy `specification.requirement` sentence do
not enter inference inputs.
Nonempty define/parameter overrides are marked incomplete until a checked
elaboration-context adapter supports them; the static source graph does not
silently assume those overrides were applied.

Each source row has `path`, `roles`, `content` and `snapshot_sha256`. Supported
roles are `testbench`, `checker`, `documentation` and `firmware`; the first
three are required for a complete common base. Paths are safe relative paths.
Each log row has `test_id`, `outcome` (`pass` or `functional_fail`), normalized
`text` and `snapshot_sha256`. A failing-run log is required. Every row binds to
the same buggy snapshot, whose identity is the canonical hash of the sorted
buggy-source path-to-SHA256 map. A hierarchy row contains only `instance`,
`module` and `path`. Keep any provenance needed to establish these declarations
in the curator archive. Hash declarations alone do not prove how a waveform or
log was produced.

The initial strict capture adapter supports the declared crypto checker
contracts. Targets with embedded executable reference models need a separately
declared reference-model tier and an admitted capture adapter before their
checker source can be exposed. This export API does not infer that admission.

## Condition directories

Every condition receives exactly the same source-only candidate inventory,
buggy RTL, selected common context and checker evidence. Candidate extraction
is rechecked from buggy source bytes, including all candidates and its explicit
unsupported/missingness records. Curator recall audits and true-site labels are
never exported.

The common `checker.json` uses `public-buggy-checker-1` and contains only the
checker context, unchanged testbench/adapter source, unchanged buggy-run log and
the verdict derived from that log. Its bytes are identical across conditions for
the same companion. Observer diagnostics, timebase, matched waveform anchors,
task windows and observational-verification metadata remain in the private
companion. They are not copied into C0/C3 or the raw-control condition through
nested checker fields. The verifier enforces the public schema and rederives its
verdict using the installed admitted checker; exported Python source is data.
Older exports containing the full private checker object must be regenerated;
their existing sealed files are never rewritten in place.

| Condition | Additional files |
|---|---|
| C0 | None |
| C1 | Source graph and candidate-to-signal alignment |
| C2 | Raw VCD windows selected from the buggy run and their indexed history |
| C3 | Fixed public specification view |
| C4 | C1, C2 and C3 files |
| M | The same raw buggy graph and selected VCD windows, plus the same specification view; aligned-only views withheld |

Waveform windows cover the observed reset through the first unchanged-checker
failure, plus passing-checkpoint task windows. Selection uses checked simulation
time and compared-signal observations, never an injection site. The raw window
projection preserves within-window record order and the state immediately
before each window; later failing task windows are withheld. The full unmodified
capture remains in the curator companion. A window requires checked anchors,
timebase and reset evidence; a missing window is not replaced with the full run.
The bounded raw adapter supports the capture observer's Icarus record layout;
unsupported layouts or directives fail explicitly.

There is no signal, graph-edge or text truncation within these declared views.
Raw window bytes are identical across C2, C4 and M for the same capture. The
`M` representation is available for development; its final study
truncation/budget policy remains a protocol decision. Heuristic, random and
learned-ranker conditions must select their declared evidence access rather
than infer an evidence bundle from their algorithm label.

For specification-enabled conditions add `--specification` and
`--specification-sha256`, using the independently recorded full-store hash.
`specification_files(store)[1]` returns the full-store identity used by this
contract. Do not create a case-specific store or choose sections from a label.
All requirement, schema and section bytes remain unchanged. `sources.json`
uses a fixed bibliography allowlist, excluding local retrieval/snapshot paths
and original per-file RTL hashes. The private provenance README is replaced
with a constant public explanation. All sections and requirements are retained;
the resulting public projection is identical across cases of the same store.
The external receipt binds both full-store and projection hashes; only the
public projection hash enters the inference manifest. Frozen stores are never
modified by export.

## Verification and execution boundary

`verify_export(path, expected_manifest_sha256=manifest_hash_from_trusted_receipt)` checks the
tree, file hashes, exact modality layout, source and candidate bindings,
read-only permissions and known leakage markers. It rejects symlinks, unsafe
paths, unexpected files and private metadata keys. Curator callers should also
pass actual private identifier strings through `forbidden_tokens` to scan for
tokens outside known case/proposal formats. Raw private paths are rejected;
logs must be normalized in the upstream evidence-preparation path.
The CLI collects known private identifier fields from the companion's private
provenance and accepts an additional curator-only `--private-token-file` list.
Neither that list nor the private provenance is copied to inference inputs.

Incomplete inputs fail by default. `--allow-partial` creates an explicitly
incomplete artifact for software development/review; it cannot pass agent
execution preflight. Unsupported graph/alignment/trace/checker state remains
missing evidence rather than being silently marked complete. A directory
marked complete concerns artifact availability, not qualification, independent
checker validity, final protocol adoption or all project prerequisites.

A read-only directory is not OS filesystem isolation. Agent execution must
add `isolation_preflight(path, expected_manifest_sha256=..., backend="bubblewrap")`
and launch the actual process using its returned `launch_prefix`. The preflight
uses an offline namespace with only the evidence tree and fixed system runtime
directories; it does not mount home directories, the curator tree, credentials
or repositories. Missing bubblewrap or an AppArmor/user-namespace rejection
blocks execution. There is no unsandboxed fallback. A provider/network bridge,
an admitted localizer runtime and project launch authorization remain separate
requirements; the preflight never authorizes a project run by itself.

The software tests use synthetic sources, logs, VCD text and specification
stores. These tests establish contract checks, not target qualification or
dataset study-readiness.
