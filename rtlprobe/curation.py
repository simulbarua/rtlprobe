"""Curator-only transitions. Public actions serialize through workspace_lock."""

from collections import Counter, defaultdict
from contextlib import nullcontext, redirect_stdout
from datetime import datetime, timezone
import io
import json
import math
from pathlib import Path
import random
import re

from . import measurement
from .evidence import CODE_ROOT, digest, filehash, identity, load, save, save_bytes, workspace_lock, write_once

DEFAULT_FIRST_N = 5
DEFAULT_FRACTION = 0.10
RANKED_STATES = {"validated_pending_review", "accepted_core", "accepted_auto", "rejected"}


def _now():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _component(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", value):
        raise ValueError("Curation identifiers must be safe filename components")
    return value


def pair(record):
    return {"design_id": record["design_id"], "operator_id": record["proposal"]["operator"]["id"]}


def _pair_key(record):
    p = pair(record)
    return p["design_id"], p["operator_id"]


def _policy_path(root, record):
    design, operator = (_component(s) for s in _pair_key(record))
    return Path(root)/"data/reviews/policy"/(design+"__"+operator+".json")


def tool_defect_hold_reasons(record):
    """Screen sealed replay observations without changing historical acceptance.

    The register-model read-back defect can produce a zero observation even
    when the DUT is correct. Unknown provenance in a mixed-oracle detector is
    also unresolved; a matching planner prediction does not resolve it.
    """
    reasons = set()
    admitted_sources = {"scoreboard_check", "sequence_tl_compare", "register_model_read_compare"}
    for replay in record.get("mutants") or []:
        signature = replay.get("signature") or []
        mixed = replay.get("oracle_kind") == "mixed_ral_read"
        if mixed and not signature:
            reasons.add("ambiguous_mixed_oracle_signature")
        for check in signature:
            source = check.get("source")
            if mixed and source not in admitted_sources:
                reasons.add("ambiguous_mixed_oracle_signature")
            if source != "register_model_read_compare":
                continue
            actual = check.get("actual")
            # Checker adapters emit decimal or 0x-prefixed hexadecimal strings.
            # X/Z values and absent/unoriented observations remain unresolved.
            if not isinstance(actual, str) or not re.fullmatch(r"(?:0[xX][0-9a-fA-F]+|[0-9]+)", actual.strip()):
                reasons.add("ambiguous_register_model_read_signature")
            elif int(actual, 16 if actual.strip().lower().startswith("0x") else 10) == 0:
                reasons.add("ral_read_zero_signature")
    return sorted(reasons)


def sealed_hold_reasons(record):
    """Only bundle fields: never consult annotations or mutable curation policy."""
    reasons = []
    if 'recovery_provenance' in record:
        reasons.append('recovered_attempt_requires_human_review')
    if record.get("automated_validation") != "pass":
        reasons.append("automated_validation_not_pass")
    if record.get("prediction_agreement") != "confirmed":
        reasons.append("prediction_agreement_not_confirmed")
    mutants = record.get("mutants") or []
    signature = (mutants[0].get("signature") or []) if mutants else []
    first = signature[0].get("id") if signature else None
    predicted = record.get("proposal", {}).get("prediction", {}).get("first_checkpoint")
    if first is None or predicted is None or first != predicted:
        reasons.append("unexpected_first_checkpoint")
    reasons.extend("check_failed:"+name for name, value in sorted(record.get("checks", {}).items())
                   if value is False)
    reasons.extend(tool_defect_hold_reasons(record))
    return reasons


def _validate(value, schema, path="receipt"):
    """Validate the JSON Schema keywords used by our fixed curation-2 schema.

    Kept local to avoid adding a non-standard-library curation dependency.
    Unsupported keywords fail closed if the schema is extended.
    """
    supported = {"$schema", "title", "description", "type", "const", "enum", "required",
                 "properties", "additionalProperties", "items", "minItems", "maxItems",
                 "minLength", "pattern", "minimum", "maximum", "exclusiveMinimum", "anyOf"}
    if set(schema) - supported:
        raise ValueError(f"Unsupported curation schema keywords: {set(schema) - supported}")
    kinds = {"object": dict, "array": list, "string": str, "integer": int,
             "number": (int, float), "null": type(None), "boolean": bool}
    if "type" in schema:
        types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(isinstance(value, kinds[t]) and not (t in {"integer", "number"} and isinstance(value, bool))
                   for t in types):
            raise ValueError(f"{path}: invalid type")
    if "const" in schema and value != schema["const"]:
        raise ValueError(f"{path}: invalid constant")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path}: invalid enum")
    if isinstance(value, dict):
        if set(schema.get("required", [])) - value.keys():
            raise ValueError(f"{path}: missing required fields")
        properties = schema.get("properties", {})
        for key, child in value.items():
            if key in properties:
                _validate(child, properties[key], path+"."+key)
            elif schema.get("additionalProperties") is False:
                raise ValueError(f"{path}: unexpected field {key}")
    if isinstance(value, list):
        if not schema.get("minItems", 0) <= len(value) <= schema.get("maxItems", math.inf):
            raise ValueError(f"{path}: invalid array size")
        for child in value:
            _validate(child, schema.get("items", {}), path+"[]")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0) or ("pattern" in schema and not re.search(schema["pattern"], value)):
            raise ValueError(f"{path}: invalid string")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if (not math.isfinite(value) or value < schema.get("minimum", -math.inf)
                or value > schema.get("maximum", math.inf)
                or value <= schema.get("exclusiveMinimum", -math.inf)):
            raise ValueError(f"{path}: invalid number")
    if "anyOf" in schema:
        for branch in schema["anyOf"]:
            try:
                _validate(value, branch, path)
                break
            except ValueError:
                pass
        else:
            raise ValueError(f"{path}: no matching receipt variant")


def validate_receipt(event):
    _validate(event, load(CODE_ROOT/"rtlprobe/schemas/curation_v2.json"))


def verify_receipt(root, summary, record):
    """New states only; legacy accepted_core verification remains in lifecycle."""
    root = Path(root)
    event_path = root/summary["acceptance_record"]
    event = load(event_path)
    validate_receipt(event)
    validation = str(Path(summary["case_path"])/"case.json")
    if (filehash(event_path) != summary["acceptance_sha256"]
            or event["case_id"] != summary["case_id"]
            or event["to_state"] != summary["state"]
            or event["case_manifest_sha256"] != summary["case_manifest_sha256"]
            or event["validation_record"] != validation
            or event["validation_sha256"] != filehash(root/validation)
            or event["policy"]["pair"] != pair(record)):
        raise ValueError("Curation receipt does not match case evidence")
    if summary["state"] == "accepted_auto":
        if sealed_hold_reasons(record) or event["policy"]["rank"] <= event["policy"]["first_n"]:
            raise ValueError("Auto acceptance has unresolved holds")
    else:
        review_path = root/summary["human_review_record"]
        review = load(review_path)
        if (event["human_review_record"] != summary["human_review_record"]
                or filehash(review_path) != summary["human_review_sha256"]
                or event["human_review_sha256"] != filehash(review_path)
                or review["manifest_sha256"] != summary["case_manifest_sha256"]
                or review["decision"] != "reject" or review["reviewer"] != event["reviewer"]):
            raise ValueError("Human rejection receipt does not match case evidence")


def _inventory(root):
    from .lifecycle import verify_index
    entries = []
    for path in sorted((Path(root)/"data/manifests").glob("*.json")):
        summary = load(path)
        if "case_path" in summary:
            record = verify_index(root, summary)
            entries.append({"summary": summary, "record": record, "path": path})
    # IDs and paths break ties without letting manifest filename order set rank.
    entries.sort(key=lambda e: (Path(e["summary"]["case_path"]).name.rsplit("-", 1)[-1],
                                e["summary"]["case_path"], e["summary"]["case_id"]))
    ranks = Counter()
    for entry in entries:
        if entry["summary"]["state"] in RANKED_STATES:
            ranks[_pair_key(entry["record"])] += 1
            entry["rank"] = ranks[_pair_key(entry["record"])]
    return entries


def _holds(root, entry, first_n):
    reasons = sealed_hold_reasons(entry["record"])
    if entry["rank"] <= first_n:
        reasons.insert(0, "first_n_human_review")
    if _policy_path(root, entry["record"]).exists():
        reasons.append("pair_under_full_review")
    return reasons


def _records(root, entry):
    cid = _component(entry["summary"]["case_id"])
    paths = {"index": entry["path"], "label": Path(root)/"data/labels"/(cid+".json"),
             "review": Path(root)/"data/reviews"/(cid+".json")}
    previous = {key+"_sha256": filehash(path) for key, path in paths.items()}
    label, review = load(paths["label"]), load(paths["review"])
    for value in (label, review):
        if value["case_id"] != cid or value["manifest_sha256"] != entry["summary"]["case_manifest_sha256"]:
            raise ValueError("Mutable record does not match case evidence")
    return paths, previous, label, review


def _event(entry, previous, destination, first_n, fraction):
    summary, record = entry["summary"], entry["record"]
    validation = str(Path(summary["case_path"])/"case.json")
    # root is inferred from the fixed index location, never from sealed host paths.
    root = entry["path"].parents[2]
    return {"schema_version": "curation-2", "case_id": summary["case_id"],
            "from_state": summary["state"], "to_state": destination,
            "reviewer": None, "human_review_record": None, "human_review_sha256": None,
            "case_manifest_sha256": summary["case_manifest_sha256"],
            "validation_record": validation, "validation_sha256": filehash(root/validation),
            "policy": {"rule": "first_n_human_then_auto", "first_n": first_n, "fraction": fraction,
                       "pair": pair(record), "rank": entry["rank"], "hold_reasons": []},
            "previous_record_hashes": previous, "recorded_at": _now()}


def _publication_files(root, cid):
    _component(cid)
    data = Path(root)/"data"
    return (data/"reviews"/(cid+".acceptance.json"), data/"reviews"/(cid+".json"),
            data/"labels"/(cid+".json"), data/"manifests"/(cid+".json"))


def _recover_publications(root):
    """Restore an interrupted transaction under the caller's workspace lock."""
    for journal in sorted((Path(root)/"data/state/curation").glob("*.json")):
        files = _publication_files(root, journal.stem)
        records = load(journal)
        if len(records) != len(files):
            raise ValueError("Incomplete curation recovery journal")
        before = [row["before"].encode() if row["before"] is not None else None for row in records]
        current = [path.read_bytes() if path.is_file() else None for path in files]
        updated = [value is not None and digest(value) == row["after_sha256"]
                   for value, row in zip(current, records)]
        if any(value != old and not new for value, old, new in zip(current, before, updated)):
            raise ValueError("Curation recovery found a record outside the saved transaction")
        if not all(updated):
            for path, value, old in zip(files, current, before):
                if value != old:
                    if old is None:
                        path.unlink()
                    else:
                        save_bytes(path, old)
        journal.unlink()


@measurement.measured('acceptance', 'acceptance_commit')
def _publish(root, entry, paths, label, event, review=None):
    """Index last. The journal restores exact prior bytes on an interrupted write."""
    validate_receipt(event)
    root = Path(root)
    cid, state = event["case_id"], event["to_state"]
    files = _publication_files(root, cid)
    event_path = files[0]
    if event_path.exists():
        old_hash = filehash(event_path)
        if event["previous_record_hashes"].get("acceptance_sha256") != old_hash:
            raise ValueError("Refusing to overwrite an unbound acceptance event")
        write_once(root/"data/reviews/history"/cid/(old_hash+".acceptance.json"), load(event_path))
    def encoded_hash(value):
        return digest((json.dumps(value, indent=2, sort_keys=True)+"\n").encode())
    summary = dict(entry["summary"], state=state, validated_pending_review=0,
                   accepted_core=int(state == "accepted_core"), accepted_auto=int(state == "accepted_auto"),
                   acceptance_record=str(event_path.relative_to(root)), acceptance_sha256=encoded_hash(event),
                   human_review_record=str(paths["review"].relative_to(root)),
                   human_review_sha256=encoded_hash(review) if review is not None else filehash(paths["review"]))
    values = (event, review, dict(label, status=state), summary)
    journal = root/"data/state/curation"/(cid+".json")
    transaction = []
    for path, value in zip(files, values):
        old = path.read_bytes() if path.exists() else None
        transaction.append(dict(before=old.decode() if old is not None else None,
                                after_sha256=encoded_hash(value) if value is not None else digest(old)))
    write_once(journal, transaction)
    try:
        for path, value in zip(files, values):
            if value is not None:
                save(path, value)
    except BaseException:
        _recover_publications(root)
        raise
    journal.unlink()
    return summary


def promote_auto(root, first_n=DEFAULT_FIRST_N, dry_run=False):
    from . import pilot
    if type(first_n) is not int or first_n < 0:
        raise ValueError("first-n must be a nonnegative integer")
    results = []
    with workspace_lock(root):
        if not dry_run:
            _recover_publications(root)
        for entry in _inventory(root):
            summary = entry["summary"]
            if summary["state"] != "validated_pending_review":
                continue
            reasons = _holds(root, entry, first_n)
            if not reasons:
                try:
                    with redirect_stdout(io.StringIO()):
                        pilot.audit(Path(root)/summary["case_path"])
                except Exception as error:
                    # Schema/checker failures also hold the case; no failed audit may promote it.
                    reasons.append("audit_failed:"+str(error))
            result = {"case_id": summary["case_id"], "pair": pair(entry["record"]),
                      "rank": entry["rank"], "reasons": reasons, "action": "HOLD" if reasons else "PROMOTE"}
            results.append(result)
            if not reasons and not dry_run:
                paths, previous, label, _ = _records(root, entry)
                event = _event(entry, previous, "accepted_auto", first_n, DEFAULT_FRACTION)
                _publish(root, entry, paths, label, event)
    return results


def accept(root, case_id, reviewer, decision, evidence, document=None, *, expected_bindings=None, publication_guard=nullcontext):
    from .lifecycle import verify_index
    _component(case_id)
    if decision not in {"approve", "reject"} or not reviewer.strip() or not evidence.strip():
        raise ValueError("A reviewer, approve/reject decision, and evidence text are required")
    root = Path(root)
    with workspace_lock(root):
        _recover_publications(root)
        entry = next((e for e in _inventory(root) if e["summary"]["case_id"] == case_id), None)
        if entry is None or entry["summary"]["state"] not in {"validated_pending_review", "accepted_auto"}:
            raise ValueError("Human decisions require a pending or accepted_auto case")
        paths, previous, label, _ = _records(root, entry)
        if expected_bindings is not None and expected_bindings != {
                **previous, 'case_manifest_sha256': entry['summary']['case_manifest_sha256']}:
            raise ValueError('Case or review changed since inspection; reload before deciding')
        first_n, fraction = DEFAULT_FIRST_N, DEFAULT_FRACTION
        if entry["summary"]["state"] == "accepted_auto":
            old_path = root/entry["summary"]["acceptance_record"]
            old = load(old_path)
            previous["acceptance_sha256"] = filehash(old_path)
            first_n, fraction = old["policy"]["first_n"], old["policy"]["fraction"]
        samples = []
        for path in sorted((root/"data/reviews/samples").glob("*.json")):
            sample = load(path)
            if case_id in sample["sample"]:
                samples.append({"record": str(path.relative_to(root)), "sha256": filehash(path)})
                fraction = sample["fraction"]
        state = "accepted_core" if decision == "approve" else "rejected"
        event = _event(entry, previous, state, first_n, fraction)
        event["policy"]["rule"] = "human_review"
        event["policy"]["hold_reasons"] = sealed_hold_reasons(entry["record"])
        review = {"case_id": case_id, "status": "reviewed", "reviewer": reviewer,
                  "decision": decision, "evidence": evidence,
                  "manifest_sha256": event["case_manifest_sha256"], "recorded_at": event["recorded_at"]}
        if document is not None:
            # Retain the document in the curator review, outside the sealed bundle.
            data = Path(document).read_bytes()
            review["document"] = {"path": str(Path(document).resolve()), "sha256": digest(data), "text": data.decode("utf-8")}
        event.update(reviewer=reviewer, human_review_record=str(paths["review"].relative_to(root)))
        # Match evidence.save's exact serialized bytes before any mutable record is replaced.
        event["human_review_sha256"] = digest((json.dumps(review, indent=2, sort_keys=True)+"\n").encode())
        validate_receipt(event)
        with publication_guard():
            if decision == "reject" and samples:
                policy_path = _policy_path(root, entry["record"])
                if not policy_path.exists():
                    write_once(policy_path, {"full_review": True, "pair": pair(entry["record"]),
                                             "rejected_case_id": case_id, "recorded_at": event["recorded_at"],
                                             "samples": samples})
            summary = _publish(root, entry, paths, label, event, review)
        verify_index(root, summary)
        return summary


def sample_auto(root, fraction=DEFAULT_FRACTION):
    if not math.isfinite(fraction) or not 0 < fraction <= 1:
        raise ValueError("fraction must be finite and greater than 0 and at most 1")
    root = Path(root)
    with workspace_lock(root):
        entries = [e for e in _inventory(root) if e["summary"]["state"] == "accepted_auto"]
        population = sorted(e["summary"]["case_id"] for e in entries)
        seed = identity(population)
        rng = random.Random(seed)
        pairs = defaultdict(list)
        for entry in entries:
            pairs[_pair_key(entry["record"])].append(entry["summary"]["case_id"])
        # One random member per pair first, then fill the overall ceil(fraction*N) quota.
        chosen = {rng.choice(sorted(pairs[p])) for p in sorted(pairs)}
        remaining = sorted(set(population) - chosen)
        chosen.update(rng.sample(remaining, max(0, math.ceil(fraction*len(population))-len(chosen))))
        result = {"population": population, "fraction": fraction, "seed": seed,
                  "sample": sorted(chosen), "recorded_at": _now(),
                  "pairs": [{"pair": {"design_id": p[0], "operator_id": p[1]}, "population": sorted(pairs[p])}
                            for p in sorted(pairs)],
                  "first_n_by_case": {e["summary"]["case_id"]:
                                      load(root/e["summary"]["acceptance_record"])["policy"]["first_n"] for e in entries}}
        path = root/"data/reviews/samples"/(result["recorded_at"]+"-"+identity(result)[:16]+".json")
        write_once(path, result)
        return path, result


def audit_data(root):
    from .lifecycle import existing_cases
    with workspace_lock(root):
        existing_cases(root)  # Retain the existing content-identity audit as well as receipt checks.
        entries = _inventory(root)
        counts = Counter({"accepted_core": 0, "accepted_auto": 0, "validated_pending_review": 0, "rejected": 0})
        pairs = {}
        withheld = []
        for entry in entries:
            summary, record = entry["summary"], entry["record"]
            counts[summary["state"]] += 1
            p = pairs.setdefault(_pair_key(record), {"pair": pair(record), "accepted_core": 0,
                                 "accepted_auto": 0, "pending": 0, "held_with_reasons": [], "rejected": 0})
            state = summary["state"]
            if state == "validated_pending_review":
                p["pending"] += 1
                reasons = _holds(root, entry, DEFAULT_FIRST_N)
                if reasons:
                    p["held_with_reasons"].append({"case_id": summary["case_id"], "rank": entry["rank"], "reasons": reasons})
            elif state in {"accepted_core", "accepted_auto", "rejected"}:
                p[state] += 1
            tool_holds = tool_defect_hold_reasons(record)
            if state in {"accepted_core", "accepted_auto"} and tool_holds:
                withheld.append({"case_id": summary["case_id"], "state": state, "reasons": tool_holds,
                                 "required_action": "corroborate_dut_fault_and_revalidate_before_study"})
        return {"scope": "saved_metadata_and_manifests", "fresh_simulations": 0, "cases": len(entries),
                "counts": dict(sorted(counts.items())), "first_n": DEFAULT_FIRST_N,
                "study_withheld_for_tool_defect": withheld,
                "pairs": [pairs[p] for p in sorted(pairs)]}
