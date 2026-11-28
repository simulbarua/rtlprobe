# Serial execution measurements

`rtlprobe.measurement` provides optional JSONL traces for a single serial Python
worker. It observes execution; it grants no authority, enforces no CPU limit,
adds no timeout, and never retries a command or a model call. Existing execution
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

The managed batch worker supports `RTLPROBE_MEASURE_DIR` on its existing launch
route. It refuses source/data destinations for tracing, without changing whether
the authorized work proceeds. Merely setting this variable does not approve or
start work. Production source deployment and refreshed runtime bindings remain
separate prerequisites. No web setting or scheduler is added by instrumentation.

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
batch setup, final backup, and time outside this worker invocation. Use the
session remainder and chronological receipts alongside per-case reports. A
paused or resumed worker needs a separate invocation trace and external queue or
human-wait timestamps before claiming end-to-end throughput.

## Boundaries and limits

| Measurement | Meaning and limitations |
|---|---|
| Verification | Controller authority checks, scoped context/recovery validation and curator evidence validation; nested calls are counted once. |
| Native commands | Launch through process exit, after the command guard. Simulation, compile/lint/synthesis and other tools have separate categories. Existing command receipts remain authoritative. |
| Capture/export | Processing spans include local capture/export work; nested tools and guards are subtracted. |
| Backup/publication/locks | Recovery creation, final backup/check, dataset/feedback/promotion publication and lock acquisition. Holding a lock is not counted as waiting for it. |
| Drive transport | The worker traces upload, listing and download calls separately. These nested spans report elapsed time and local process CPU. Commands, paths, credentials and response bodies are omitted from the trace. |
| Acceptance commit | A distinct span covers the journaled curation transaction through index publication and journal removal. Measure guard and decision work in their surrounding spans. Human review time and decisions made outside the traced worker require separate evidence. |
| Model transport | Local Docker role submission through response, including helper startup/teardown. Local preflight/postflight is separate. Provider queue, network, generation and wrapper work cannot be split by this boundary. Attempts/completions are not a billable-call ledger. |
| CPU | `getrusage` deltas for this process and reaped children. Docker-daemon descendants, remote provider compute, live un-reaped children and other host services are outside this accounting. Process-wide counters assume serial ownership. |
| Memory | Process lifetime RSS high-water mark and maximum reaped-child RSS, normalized to bytes. Neither is concurrent process-tree peak memory. |
| Disk | Logical regular-file bytes at operation completion/failure and before native commands. Includes neither temporary peak usage nor unrelated backup/export storage. Missing/inaccessible inventories are unknown. |

Output inventory is measured as instrumentation overhead and does not scan the
whole dataset. Telemetry writes also have a cost; measure it on the actual staging
host. No caching or reduced verification is implemented by these measurements.

## Whole-host sampling

The companion agent utility `python -m rtlprobe_agents.serial_measurement`
supports `summarize TRACE`, read-only Linux `sample-host` and
`summarize-host SAMPLES`. Sampling requires
an explicit external output file, sample count, and optional confirmed provider
window and cgroup paths. It records aggregate `/proc/stat` counters, CPU steal,
load averages, runnable count, and supplied cgroup CPU/memory/process counters.
Guest CPU busy excludes steal and iowait; guest counters alone cannot establish
credit balance, recovery, throttling cause or runnable CPU demand.

The host summary uses elapsed counter deltas for aggregate CPU and reports
busy, steal, and I/O wait. Each cgroup's busy percentage uses all allocated
logical CPUs as the denominator. The summary reports cgroup coverage and
intervals missing a usable counter. A parent cgroup includes its sampled
descendants, so sum only disjoint groups. The rolling-window counts describe
guest telemetry.
