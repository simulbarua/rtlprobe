# Mutation operators and candidate extraction

The executable [operator registry](../rtlprobe/operators.json) defines IDs,
versions, approval, applicability and exclusions. The mapper verifies the source
hash and exact syntax/token span before applying a single edit. It rejects
unsupported or ambiguous sites; it does not repair source to make a site parse.

## Approved operators

| ID | Edit | Important constraints |
|---|---|---|
| `unsigned32_root_add_to_sub` | Replace a supported root addition with subtraction | Narrow unsigned 32-bit assignment shape |
| `literal_lsb_flip32` | Flip the least-significant bit of a supported 32-bit literal | Supported unsigned register/localparam context; not arbitrary function-return table entries |
| `relational_operator_replace` | Swap `>=`/`>`, `<=`/`<`, or `==`/`!=` | Known-width operands; no case-equality, macro-derived or ambiguous sites |
| `condition_invert` | Invert an `if` condition or ternary selector | Reset, macro-derived and generated sites excluded; study candidate rule must include conditions before case use |
| `logic_operator_swap` | Swap binary bitwise AND/OR or logical AND/OR | Known-width operands; unary reductions and assertion/cover constructs excluded |

All five currently have `approved` registry status. Operator approval is separate
from target qualification, candidate-rule adoption and case acceptance. Consult
the registry for the complete per-operator preconditions and exclusions.

Mutation location and application use pinned `pyslang==12.0.0` for Verilog and
SystemVerilog. Historical mapper identifiers remain provenance only; recorded
source identities and freshly derived spans must still agree. Pyverilog remains
a dependency of the experimental localization graph, not the mutation mapper.

## Read-only inspection

From the repository root, using a Python environment with the pinned requirements:

```sh
python scripts/operator_regression.py --data-root /absolute/rtlprobe-data
python scripts/operator_sites.py --manifest targets/sha256/config.json --source-root /absolute/original-source-root
```

Both commands print JSON without writing dataset files or running simulations.
The regression command re-derives accepted cases' patches in memory and compares
their bytes with saved patches. The site inventory counts operator/site
combinations, not independently accepted bugs or guaranteed test detections.

The current inventory API parses standalone files with default parameters.
OpenTitan top files requiring include/package/define context can be rejected.
Inspect the returned diagnostics and partial status; unknown counts are not zero.

## Candidate syntax versus dependency graphs

`rtlprobe.candidates.extract_candidates` enumerates source locations independently
of the operator registry and labels: assignments, parameters, supported binary
expressions, and `if`/ternary conditions. It groups by source file/module/line
while retaining constituent spans. Study scoring must declare line versus
statement/span semantics.

This syntax inventory does not elaborate a dependency graph. The
[localization experiment](localization.md) still has a restricted graph parser;
functions, generate constructs, parameter overrides and instance arrays can be
inventoried syntactically while remaining unsupported by that graph. Mapping an
operator site to a candidate does not establish localization readiness.

## Versioned source candidate contract

The implemented rule is `source-syntax-line-v2`, with inventory schema
`candidate-inventory-1`. This identifies a software contract; the study's final
candidate/scoring/tie policy still requires explicit adoption and freeze. It
does not release any execution hold or qualify a target.

`extract_candidates(sources)` accepts only a mapping of canonical repository
paths to source text or bytes. It reads no registry, labels, cases, execution
outcomes or external files. It includes simple blocking/nonblocking assignments,
initialized declarators, simple `if` and ternary predicates (including resets),
and supported comparison and AND/OR expressions. It groups all constituent
constructs with the same file, module and anchor line into one candidate.
Uninitialized declarations, compound assignments/standalone calls, non-module
scopes, assertion/property/sequence contexts and unmappable/macro-derived sites
are outside this rule. Pattern or multiple predicates are reported unsupported.
The exact policy is returned by `rule_contract()` and included in every inventory.

Each row retains `path`, `module`, one-based anchor `line`, source text,
`syntax_kinds`, `lhs`, `dependencies` and `site_spans`. Source names are syntax
identifiers, not proof of elaborated signal connectivity. Spans use zero-based
half-open byte offsets plus one-based start/end line and column. Current parsing
requires ASCII standalone source; unsupported encoding and include/package/macro
context produce explicit diagnostics. CRLF bytes are preserved. Candidate IDs
bind the rule, source hash, path, module and anchor line. `source_hashes` binds
all supplied files, and `inventory_id` binds the complete canonical inventory.
`validate_inventory(inventory, sources=...)` checks identities and exact source
re-extraction before an exporter projects allowed fields.

`file_status` distinguishes a complete count, a partial count with diagnostics,
and a rejected file whose count is `null` (unknown, never a measured zero).
`status`, `coverage`, `rejected` and `excluded` retain these distinctions. The
inventory also declares dependency elaboration and signal/time mapping as
`not_provided`. Functions, generate regions, parameterized instances and instance
arrays may have source candidates while still requiring separate checked
hierarchy/dependency mapping. No syntax count establishes all-evidence readiness.

Every evidence condition consumes the same complete source inventory and
`inventory_id`. Missing graph, trace or specification evidence must be represented
by missingness, not by dropping candidates. No outcome-dependent shortlist is part
of extraction. If later evaluation intentionally filters candidates, preserve the
original universe and report omissions rather than silently improving recall.

`audit_recall(inventory, true_sites, match=..., retained_candidate_ids=...)` is a
separate **curator-only** audit. Its labels and returned per-site audit must never
enter inference exports. The caller must choose `line` or `span` explicitly:

- `line` matches path and exact candidate anchor line; module is additionally
  matched if supplied. A multiline statement's later lines are not silently
  treated as anchor lines.
- `span` matches path and an exact constituent `[start_byte, end_byte)` pair;
  module is additionally matched if supplied. Curators must supply coordinates
  in the inventoried snapshot, not stale original offsets after a length-changing
  edit. An optional true-site `source_sha256` rejects another snapshot's mapping.

The audit reports mapped/missed sites and recall, keeps omitted true sites in the
denominator as misses, and returns `null` recall for an empty truth set. It does
not rank candidates, choose a metric or resolve ties (`tie_policy: not_selected`).
`mapping_coverage` remains a separate curator operator-site audit with exact
constituent spans. Neither audit changes or selects the inference universe.
