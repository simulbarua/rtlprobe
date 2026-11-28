# Serial execution measurements

`rtlprobe.measurement` provides optional JSONL traces for a single serial Python
worker. It observes execution; it grants no authority, enforces no CPU limit,
adds no timeout, and never retries a command. Existing execution
guards and receipt formats still apply. Traces are diagnostic records, not
acceptance evidence.

Use a fresh external directory outside source, protected dataset and sealed
evidence roots. No trace is written unless a measurement session is enabled:

```python
from rtlprobe import measurement

with measurement.session("/external/measurements", fixture=True):
    with measurement.span("example", "verification"):
        verify_existing_fixture()
```

Each trace has a unique filename, session identity, monotonic start/end samples,
parent span IDs, case identity where applicable, outcome, elapsed time and CPU
counters. Nested spans are inclusive in the trace. The report subtracts each
direct child's duration and CPU once, producing exclusive stage totals. The
unattributed remainder is reported explicitly. Error outcomes retain their spans;
an interrupted/truncated trace cannot establish complete coverage. Output-open
or write failures warn on stderr and leave execution policy unchanged.

```python
import json
from pathlib import Path
from rtlprobe.measurement import summarize

events = [json.loads(line) for line in Path("/external/measurements/trace.jsonl").read_text().splitlines()]
print(json.dumps(summarize(events), indent=2))
```

Coverage is the fraction assigned to named stages, not proof that every
sub-operation within a stage is understood. Per-case totals sum intervals tagged
with that case, including its later review/promotion spans; they exclude shared
batch setup and time outside the measured session. Use the session remainder
and chronological receipts alongside per-case reports.

## Boundaries and limits

| Measurement | Meaning and limitations |
|---|---|
| Verification | Runner input and evidence validation. Nested calls are counted once. |
| Native commands | Launch through process exit, after the command guard. Simulation, compile/lint/synthesis and other tools have separate categories. Existing command receipts remain authoritative. |
| Capture/export | Processing spans include local capture/export work; nested tools and guards are subtracted. |
| Publication and locks | Dataset publication and lock acquisition. Holding a lock is distinct from waiting for it. |
| Acceptance commit | A distinct span covers the journaled curation transaction through index publication and journal removal. Measure guard and decision work in their surrounding spans. Human review time and decisions made outside the traced worker require separate evidence. |
| CPU | `getrusage` deltas for this process and reaped children. Container processes outside the process tree, unreaped children, and other workloads are outside this accounting. Process-wide counters assume serial ownership. |
| Memory | Process lifetime RSS high-water mark and maximum reaped-child RSS, normalized to bytes. Neither is concurrent process-tree peak memory. |
| Disk | Logical regular-file bytes at operation completion/failure and before native commands. Includes neither temporary peak usage nor unrelated storage. Missing/inaccessible inventories are unknown. |

Output inventory is measured as instrumentation overhead and does not scan the
whole dataset. Telemetry writes also have a cost; measure it in the environment used for the experiment. No caching or reduced verification is implemented by these measurements.
