"""Content identity, immutable publication, and bounded whole-case recovery."""

import os
from pathlib import Path

from .evidence import filehash, identity, load, save, verify_manifest, write_once


def mutation_key(config, source_hashes, path, changed_sha256):
    hashes = {p: source_hashes[p] for p in config["rtl"] + [config["testbench"]]}
    hashes[path] = changed_sha256
    return identity({"repository": config["repository_url"], "revision": config["revision"],
                     "buggy_files": hashes, "configuration": {k: config[k] for k in
                         ("top", "test_top", "compile_flags", "defines", "parameters", "seed")}})


def verify_index(root, summary):
    out = Path(root)/summary["case_path"]
    verify_manifest(out)
    if filehash(out/"manifest.json") != summary["case_manifest_sha256"]:
        raise ValueError("Published case manifest changed")
    record = load(out/"case.json")
    if record["case_id"] != summary["case_id"]:
        raise ValueError("Published case ID mismatch")
    if summary["state"] == "accepted_core":
        event_path = Path(root)/summary["acceptance_record"]
        review_path = Path(root)/summary["human_review_record"]
        event, review = load(event_path), load(review_path)
        if (filehash(event_path) != summary["acceptance_sha256"]
                or filehash(review_path) != summary["human_review_sha256"]
                or event["human_review_sha256"] != filehash(review_path)
                or event["case_manifest_sha256"] != summary["case_manifest_sha256"]
                or review["manifest_sha256"] != summary["case_manifest_sha256"]
                or event["to_state"] != "accepted_core" or review["decision"] != "approve"):
            raise ValueError("Human approval receipt does not match case evidence")
    elif summary["state"] != record["state"]:
        raise ValueError("Case state disagrees with published summary")
    return record


def existing_cases(root):
    result = {}
    for path in sorted((Path(root)/"data/manifests").glob("*.json")):
        summary = load(path)
        if "case_path" not in summary:
            continue
        record = verify_index(root, summary)
        out = Path(root)/summary["case_path"]
        fp = load(out/"fingerprint.json")["inputs"]
        proposal = record["proposal"]
        buggy = out/"rtl/buggy"/proposal["path"]
        if not buggy.exists():
            # Invalid pre-application cases carry the preflight content key.
            key = record["mutation_key"]
        else:
            key = mutation_key(fp["config"], fp["files"], proposal["path"], filehash(buggy))
        if record.get("mutation_key", key) != key:
            raise ValueError("Content identity disagrees with case record")
        result[key] = summary
    return result


def reserve_attempt(root, key, fingerprint, new_directory):
    """Caller holds workspace lock. Completed-but-unpublished bundles are recoverable."""
    root = Path(root)
    path = root/"data/state"/(key+".json")
    state = load(path) if path.exists() else {"mutation_key": key, "fingerprint": fingerprint, "attempts": []}
    if state["fingerprint"] != fingerprint:
        raise ValueError("Cannot resume an unfinished case with changed inputs/environment")
    if state["attempts"]:
        previous = state["attempts"][-1]
        out = root/previous["path"]
        if (out/"manifest.json").exists():
            verify_manifest(out)
            return state, out, True
        for process_file in out.glob("commands/*/process.json"):
            if (process_file.parent/"run.json").exists():
                continue
            pid = load(process_file)["pid"]
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                pass
            else:
                raise RuntimeError("An interrupted attempt may still have a live tool process; refusing concurrent recovery")
        previous["status"] = "interrupted"
        write_once(out/"INTERRUPTED.json", {"status": "interrupted", "reason": "No sealed terminal case; preserving partial artifacts"})
    if len(state["attempts"]) >= 2:
        raise RuntimeError("Interrupted-case retry budget exhausted (maximum two attempts)")
    out = new_directory()
    state["attempts"].append({"path": str(out.relative_to(root)), "status": "running"})
    save(path, state)
    return state, out, False


def complete_attempt(root, state, record):
    state["attempts"][-1]["status"] = record["state"]
    save(Path(root)/"data/state"/(state["mutation_key"]+".json"), state)


def publish(root, out, record):
    root, out = Path(root), Path(out)
    verify_manifest(out)
    cid = record["case_id"]
    manifest_sha = filehash(out/"manifest.json")
    summary_path = root/"data/manifests"/(cid+".json")
    if summary_path.exists():
        existing = load(summary_path)
        verify_index(root, existing)
        if existing["case_manifest_sha256"] != manifest_sha:
            raise ValueError("Cannot overwrite a published case or its human decision")
        return existing
    if record["state"] == "validated_pending_review":
        patch = root/"data/patches"/(cid+".patch")
        patch.parent.mkdir(parents=True, exist_ok=True)
        data = (out/"mutation.patch").read_bytes()
        if patch.exists() and patch.read_bytes() != data:
            raise ValueError("Refusing to overwrite an existing patch")
        if not patch.exists():
            with patch.open("xb") as stream:
                stream.write(data)
        write_once(root/"data/labels"/(cid+".json"), {"case_id": cid, "status": "pending_human",
                   "ground_truth": record["ground_truth"], "manifest_sha256": manifest_sha,
                   "source_kind": "synthetic_semantic", "model_access": "evaluator_only"})
        write_once(root/"data/reviews"/(cid+".json"), {"case_id": cid, "status": "pending",
                   "reviewer": None, "decision": None, "manifest_sha256": manifest_sha})
    summary = {"schema_version": "pilot-2", "case_id": cid, "mutation_key": record["mutation_key"],
               "case_path": str(out.relative_to(root)), "case_manifest_sha256": manifest_sha,
               "state": record["state"], "attempted_candidates": 1,
               "validated_pending_review": int(record["state"] == "validated_pending_review"),
               "accepted_core": 0, "distinct_sites": 1, "cost": record["cost"]}
    write_once(summary_path, summary)
    return summary
