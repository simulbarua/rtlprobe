"""Execute standard mutation proposals from any client, with optional sealed bundles."""
import json
from pathlib import Path
from . import batch
from .evidence import filehash, verify_manifest


def run(path, expected_manifest_sha256=None):
    path = Path(path).resolve()
    bundle = path if path.is_dir() else None
    proposals = bundle/'mutations.jsonl' if bundle else path
    if expected_manifest_sha256 is not None and bundle is None:
        raise ValueError('A manifest hash requires a sealed bundle directory')
    def validate(actual, design, config, fingerprint):
        if bundle is not None:
            if expected_manifest_sha256 is not None and filehash(bundle/'manifest.json') != expected_manifest_sha256:
                raise ValueError('Execution bundle differs from the caller-validated manifest')
            verify_manifest(bundle)
            saved = [json.loads(s) for s in proposals.read_text().splitlines() if s.strip()]
            if actual != saved:
                raise ValueError('Execution proposals changed while reading bundle')
    # batch.run independently validates source mapping, operators, qualification,
    # resource policy, functional failures/restoration and required tool evidence.
    return batch.run(proposals, validate_plan=validate)
