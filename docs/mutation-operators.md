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
