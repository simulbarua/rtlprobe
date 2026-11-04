"""Execute reviewed mutation proposals, with sealed inputs and separate review receipts."""
import json
from datetime import datetime
from pathlib import Path
from . import batch
from .evidence import filehash, load, treehashes

REVIEW_SIDECARS = {'PLAN_REVIEW.md', 'plan_review.json'}


def verify_bundle(directory):
    """Verify sealed plan files; only the two declared review sidecars may be added."""
    directory = Path(directory)
    sealed = load(directory/'manifest.json')
    expected = sealed['files']
    if REVIEW_SIDECARS & set(expected):
        raise ValueError('Review sidecars must be outside the frozen plan manifest')
    actual = {k: v for k, v in treehashes(directory).items()
              if k != 'manifest.json' and k not in REVIEW_SIDECARS}
    if actual != expected:
        raise ValueError('Artifact manifest mismatch (missing, changed, or additional files)')
    for name in REVIEW_SIDECARS:
        if (directory/name).is_symlink():
            raise ValueError('Review sidecars cannot be symlinks')
    return sealed


def review_decisions(directory, proposals, expected_manifest_sha256=None):
    """Return rejected proposal IDs; missing, incomplete and stale reviews fail closed."""
    directory = Path(directory)
    digest = filehash(directory/'manifest.json')
    if expected_manifest_sha256 is not None and digest != expected_manifest_sha256:
        raise ValueError('Execution bundle differs from the caller-validated manifest')
    path = directory/'plan_review.json'
    if not path.is_file():
        raise ValueError('A recorded pre-injection plan review is required')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate plan review key')
            result[key] = value
        return result
    review = json.loads(path.read_text(), object_pairs_hook=unique)
    if (not isinstance(review, dict) or set(review) != {'schema_version', 'plan_manifest_sha256', 'reviewer', 'reviewed_at', 'decisions'}
            or review['schema_version'] != 'plan-review-1' or review['plan_manifest_sha256'] != digest
            or not isinstance(review['reviewer'], str) or not review['reviewer'].strip()):
        raise ValueError('Invalid or stale plan review')
    try:
        when = datetime.fromisoformat(review['reviewed_at'].replace('Z', '+00:00'))
        if when.tzinfo is None:
            raise ValueError('timezone required')
    except (ValueError, TypeError, AttributeError):
        raise ValueError('Plan review requires a timezone-qualified reviewed_at') from None
    ids = [p['proposal_id'] for p in proposals]
    if len(ids) != len(set(ids)) or not isinstance(review['decisions'], list):
        raise ValueError('Plan review proposal identities are ambiguous')
    decisions = {}
    for item in review['decisions']:
        if (not isinstance(item, dict) or set(item) != {'proposal_id', 'decision', 'note'}
                or not isinstance(item['proposal_id'], str) or item['proposal_id'] in decisions
                or not isinstance(item['decision'], str) or item['decision'] not in {'approve', 'reject', 'edit'}
                or not isinstance(item['note'], str)):
            raise ValueError('Invalid or duplicate plan review decision')
        decisions[item['proposal_id']] = item['decision']
    if set(decisions) != set(ids):
        raise ValueError('Plan review must decide every proposal exactly once')
    if 'edit' in decisions.values():
        raise ValueError('Edited proposals require a replacement proposal and fresh plan')
    return {pid for pid, decision in decisions.items() if decision == 'reject'}


def run(path, expected_manifest_sha256=None, *, execution_guard=None):
    bundle = Path(path).resolve()
    if not bundle.is_dir():
        raise ValueError('Execution requires a sealed bundle directory with recorded plan review')
    proposals = bundle/'mutations.jsonl'
    def validate(actual, design, config, fingerprint):
        if expected_manifest_sha256 is not None and filehash(bundle/'manifest.json') != expected_manifest_sha256:
            raise ValueError('Execution bundle differs from the caller-validated manifest')
        verify_bundle(bundle)
        saved = [json.loads(s) for s in proposals.read_text().splitlines() if s.strip()]
        if actual != saved:
            raise ValueError('Execution proposals changed while reading bundle')
        rejected = review_decisions(bundle, actual, expected_manifest_sha256)
        if any(p['proposal_id'] not in rejected and p.get('operator', {}).get('id') == 'condition_invert'
               for p in actual):
            raise ValueError('condition_invert case use is blocked until the adopted candidate-universe rule (T-19) is implemented')
        return rejected
    options = {} if execution_guard is None else {'execution_guard': execution_guard}
    return batch.run(proposals, validate_plan=validate, **options)
