"""Bounded target-selected campaigns with immutable cases and whole-case recovery."""

import argparse
from collections import Counter
import difflib
import json
from pathlib import Path
import shutil
import time

from . import pilot
from .evidence import (ROOT, CommandError, Runner, filehash, identity, load, manifest,
                       save, treehashes, verify_manifest, workspace_lock, write_once)
from .lifecycle import (complete_attempt, existing_cases, mutation_key, publish,
                        reserve_attempt, verify_index)
from .mutation import apply, safe_path, sha


def operator_for(proposal):
    matches = [o for o in load(pilot.REGISTRY)["operators"] if
               {"id": o["id"], "version": o["version"]} == proposal["operator"]]
    if len(matches) != 1 or matches[0]["status"] != "approved":
        raise ValueError("Unknown or unapproved operator")
    return matches[0]


def preflight(proposal, config, fp):
    pilot.schema(proposal, "proposal")
    path = str(safe_path(proposal["path"]))
    if path not in config["rtl"]:
        raise ValueError("Mutation must target declared RTL, never the testbench")
    before = (ROOT/config["vendor"]/path).read_bytes()
    after = apply(before, proposal["target"], operator_for(proposal))
    key = mutation_key(config, fp["inputs"]["files"], path, sha(after))
    return key, before, after


def review_text(record):
    p = record["proposal"]
    original = p["target"]["statement"]
    # Full exact edit is in mutation.patch; the statement is shown without guessing offsets after indentation.
    lines = [f"# Review {record['case_id']}", "", f"State: **{record['state']}**.", "",
             f"Site: `{p['path']}:{p['target']['line']}`. Family: `{p['family']}`.", "",
             p.get("mechanism", p["activation"]), "", f"Original statement: `{original}`.",
             f"Exact token: `{p['target']['before']}` → `{p['target']['after']}`. See mutation.patch.", "",
             "| Gate | Observed result |", "|---|---|"]
    for name in ("original", "restored"):
        lines.append(f"| {name} | {(record.get(name) or {}).get('outcome', 'not_run')} |")
    for i, result in enumerate(record["mutants"], 1):
        lines.append(f"| mutant {i} | {result['outcome']} |")
    lines += [f"| structural checks | {record['structural']['buggy']['status']} |",
              f"| prediction agreement | {record['prediction_agreement']} |", ""]
    if record["mutants"] and record["mutants"][0]["signature"]:
        lines += ["| Checkpoint | Expected | Actual |", "|---|---|---|"]
        for check in record["mutants"][0]["signature"]:
            lines.append(f"| {check['id']} | `{check['expected']}` | `{check['actual']}` |")
    lines += ["", "The checker and expected values are unchanged. This is a synthetic semantic defect; all artifacts are curator-only.",
              "Review the patch, requirement, causal site, replay/restoration logs, and manifest before approving. Human review is pending."]
    return "\n".join(lines)+"\n"


def execute(proposal, config, fp, design, key, before, after, out, remaining):
    runner = Runner(out, {**config["limits"], "campaign_seconds": remaining})
    save(out/"proposal.json", proposal)
    save(out/"fingerprint.json", fp)
    path = proposal["path"]
    original, buggy, restored = [out/p for p in ("rtl/original", "rtl/buggy", "rtl/restored")]
    record = {"schema_version": "pilot-2", "case_id": config["case_prefix"]+"-"+key[:16], "mutation_key": key,
              "state": "needs_review", "automated_validation": "fail", "design_id": config["design_id"],
              "proposal": proposal, "fingerprint": fp["sha256"], "track": config["track"],
              "original": None, "mutants": [], "restored": None, "checks": {},
              "structural": {"original": {**design["structure"], "reused_from": design["evidence"]},
                             "buggy": {"status": "not_run"}}, "qualification": design["evidence"],
              "prediction_agreement": "not_assessed", "human_review": {"status": "pending", "reviewer": None, "decision": None},
              "ground_truth": {"path": path, "line_1based": proposal["target"]["line"],
                               "statement": proposal["target"]["statement"], "edit": proposal["target"],
                               "lineage_id": proposal["lineage_id"], "review_status": "pending_human"},
              "access": "curator_only; no localization-model export implemented"}
    try:
        pilot.snapshot(config, original)
        if (original/path).read_bytes() != before:
            raise ValueError("Source changed after preflight")
        shutil.copytree(original, buggy)
        (buggy/path).write_bytes(after)
        patch = out/"mutation.patch"
        patch.write_text("".join(difflib.unified_diff(before.decode().splitlines(True), after.decode().splitlines(True),
                                                   fromfile="a/"+path, tofile="b/"+path)))
        record["original"] = pilot.simulate(runner, config, "original", original,
                                             pilot.compile_design(runner, config, "original", original))
        if record["original"]["outcome"] != "pass":
            raise RuntimeError("Shared original/checker failure; stop campaign")
        binary = pilot.compile_design(runner, config, "mutant", buggy)
        record["mutants"].append(pilot.simulate(runner, config, "mutant_1", buggy, binary))
        if record["mutants"][0]["outcome"] == "functional_fail":
            for i in (2, 3):
                record["mutants"].append(pilot.simulate(runner, config, f"mutant_{i}", buggy, binary))
        shutil.copytree(buggy, restored)
        runner.require("reverse_patch", ["patch", "-p1", "-R", "-i", patch], restored, 10)
        record["restored"] = pilot.simulate(runner, config, "restored", restored,
                                             pilot.compile_design(runner, config, "restored", restored))
        checks = pilot.gates(record["original"], record["mutants"], record["restored"],
                             treehashes(original) == treehashes(restored))
        record["checks"] = checks
        first = record["mutants"][0]["outcome"]
        if first == "pass":
            record["state"] = "unexposed"
            record["prediction_agreement"] = "not_exposed"
        elif first != "functional_fail":
            record["state"] = "infrastructure_error"
        elif not checks["three_consistent_mutant_failures"]:
            record["state"] = "flaky"
        elif all(checks.values()):
            record["structural"]["buggy"] = pilot.structure(runner, config, "mutant", buggy)
            checks["synthesis"] = all(s["status"] == "pass" for s in record["structural"].values())
            checks["unchanged_checker"] = filehash(original/config["testbench"]) == filehash(buggy/config["testbench"])
            checks["single_changed_rtl_file"] = [p for p, h in treehashes(original).items() if treehashes(buggy).get(p) != h] == [path]
            checks["unchanged_environment"] = pilot.fingerprint(config) == fp
            if all(checks.values()):
                record["state"] = "validated_pending_review"
                record["automated_validation"] = "pass"
                record["prediction_agreement"] = ("confirmed" if record["mutants"][0]["signature"][0]["id"] ==
                                                   proposal["prediction"]["first_checkpoint"] else "unexpected_failure_needs_review")
        if record["restored"]["outcome"] != "pass" or not checks["restored_source_identity"]:
            record["state"] = "needs_review"
    except CommandError as error:
        record["error"] = str(error)
        command = error.record
        if command["timed_out"]:
            record["state"] = "infrastructure_error"
        elif command["id"] == "mutant_compile":
            record["state"] = "invalid"
        elif command["id"] in ("mutant_lint", "mutant_synthesis"):
            record["state"] = "unsupported"
        else:
            record["state"] = "infrastructure_error"
    except (ValueError, RuntimeError) as error:
        record["state"] = "needs_review"
        record["error"] = str(error)
    record["cost"] = {"command_elapsed_seconds": sum(c["elapsed_seconds"] for c in runner.records),
                      "child_cpu_seconds": sum(c["cpu_seconds"] for c in runner.records),
                      "human_review_minutes": None}
    pilot.schema(record, "case")
    save(out/"case.json", record)
    (out/"REVIEW.md").write_text(review_text(record))
    manifest(out)
    return record


def run(proposal_path, cap=10, validate_plan=None):
    # Entire read-check-execute-publish transaction is protected against concurrent writers.
    with workspace_lock():
        design, config, fp = pilot.qualified()
        proposals = [json.loads(s) for s in Path(proposal_path).read_text().splitlines() if s.strip()]
        if validate_plan is not None:
            validate_plan(proposals, design, config, fp)
        if not 1 <= len(proposals) <= min(cap, 10):
            raise ValueError("Campaign must contain 1 to 10 proposals")
        sites = [(p["path"], p["target"]["line"]) for p in proposals]
        if len(set(sites)) != len(sites):
            raise ValueError("Campaign contains repeated source sites")
        prepared = [(p, *preflight(p, config, fp)) for p in proposals]
        existing = existing_cases(ROOT)
        for p, key, _, _ in prepared:
            if key in existing:
                continue  # Existing evidence is referenced, never silently revalidated or overwritten.
            if p["baseline_fingerprint"] != fp["sha256"] or p["registry_sha256"] != filehash(pilot.REGISTRY):
                raise ValueError("Proposal inputs are stale; create a new frozen plan")
            if p["primary_test"] != config["test_id"] or p["fallback_tests"] or p["limits"] != config["limits"]:
                raise ValueError("Unsupported tests or changed resource policy")
        bid = "batch-"+identity(proposals)[:16]
        directory = ROOT/"outputs"/config["target_id"]/"batches"/bid
        directory.mkdir(parents=True, exist_ok=True)
        write_once(directory/"plan.json", proposals)
        started = time.monotonic()
        invocation = directory/"invocations"/(str(time.time_ns())+".json")
        executed_this_invocation = recovered_this_invocation = 0
        results = []
        for proposal, key, before, after in prepared:
            if key in existing:
                summary = existing[key]
                results.append({"proposal_id": proposal["proposal_id"], "disposition": "duplicate", **summary})
                print(f"REUSED {summary['case_id']} {summary['state']}", flush=True)
            else:
                # Charge preserved attempts, including interrupted work, against this bounded campaign.
                elapsed, cpu, disk = campaign_usage([k for _, k, _, _ in prepared])
                remaining = min(config["limits"]["campaign_seconds"]-elapsed,
                                config["limits"]["campaign_seconds"]-(time.monotonic()-started))
                if remaining <= 0 or cpu >= config["limits"]["cpu_seconds"] or disk >= config["limits"]["disk_bytes"]:
                    raise RuntimeError("Campaign resource budget exhausted; completed cases preserved")
                state, out, recovered = reserve_attempt(ROOT, key, fp["sha256"], lambda: pilot.new_output("cases", config["case_prefix"]+"-"+key[:16], config))
                if recovered:
                    recovered_this_invocation += 1
                    record = load(out/"case.json")
                    if record["mutation_key"] != key or record["fingerprint"] != fp["sha256"]:
                        raise ValueError("Recovered terminal case identity mismatch")
                else:
                    executed_this_invocation += 1
                    record = execute(proposal, config, fp, design, key, before, after, out, remaining)
                if record["state"] == "validated_pending_review":
                    pilot.audit(out)  # Re-parse actual logs and verify hashes before publication.
                summary = publish(ROOT, out, record)
                complete_attempt(ROOT, state, record)
                existing[key] = summary
                results.append({"proposal_id": proposal["proposal_id"], "disposition": record["state"], **summary})
                print(f"{record['state'].upper()} {record['case_id']}", flush=True)
            report = {"schema_version": "batch-1", "batch_id": bid, "plan_sha256": filehash(directory/"plan.json"),
                      "planned_candidates": len(proposals), "processed_candidates": len(results), "cases": results,
                      "status": "completed" if len(results) == len(proposals) else "running",
                      "executed_this_invocation": executed_this_invocation,
                      "recovered_this_invocation": recovered_this_invocation,
                      "duplicates_this_invocation": sum(r["disposition"] == "duplicate" for r in results),
                      "counts": dict(Counter(r["state"] for r in results)),
                      "newly_accepted_core": 0, "newly_accepted_auto": 0, "budget": config["limits"],
                      "cost": dict(zip(("command_elapsed_seconds", "child_cpu_seconds", "artifact_bytes"),
                                       campaign_usage([k for _, k, _, _ in prepared])))}
            save(directory/"report.json", report)
            save(invocation, report)
            if results[-1]["state"] in {"infrastructure_error", "needs_review"}:
                raise RuntimeError("Campaign paused for unresolved execution/evidence failure; inspect case record")
        print(f"BATCH_REPORT {directory/'report.json'}", flush=True)
        return report


def campaign_usage(keys):
    elapsed = cpu = disk = 0
    for key in keys:
        state_path = ROOT/"data/state"/(key+".json")
        if not state_path.exists():
            continue
        for attempt in load(state_path)["attempts"]:
            out = ROOT/attempt["path"]
            for start in out.glob("commands/*/started.json"):
                run_path = start.parent/"run.json"
                if run_path.exists():
                    rec = load(run_path)
                    elapsed += rec["elapsed_seconds"]
                    cpu += rec["cpu_seconds"]
                else:
                    # Conservatively reserve the whole command limit when completion is unknown.
                    elapsed += load(start)["timeout_seconds"]
                    cpu += load(start)["timeout_seconds"]
            disk += sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    return elapsed, cpu, disk


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="mode", required=True)
    run_parser = subs.add_parser("run")
    run_parser.add_argument("proposals")
    args = parser.parse_args()
    run(args.proposals)


if __name__ == "__main__":
    main()
