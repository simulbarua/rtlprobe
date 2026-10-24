"""Hash-checked, idempotent application to exported copies only."""
from pathlib import Path
import re
import tarfile

from ..evidence import CODE_ROOT, digest, filehash, load
from ..mutation import safe_path

HOME = CODE_ROOT / 'tooling/verilator-uvm'
MANIFEST = HOME / 'patches/manifest.json'


def patched_bytes(original, patch):
    """Apply the exact unified diff, without offsets, fuzz, or shell execution."""
    lines = original.decode().splitlines(keepends=True)
    diff = patch.splitlines(keepends=True)
    out, pos, i = [], 0, 2
    while i < len(diff):
        match = re.fullmatch(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@.*\n?', diff[i])
        if not match:
            raise ValueError('Invalid unified diff hunk')
        start = max(0, int(match[1]) - 1)
        if start < pos:
            raise ValueError('Overlapping patch hunks')
        out.extend(lines[pos:start]); pos = start; i += 1
        old_count = new_count = 0
        while i < len(diff) and not diff[i].startswith('@@ '):
            line = diff[i]; i += 1
            if line[:1] in (' ', '-'):
                if pos >= len(lines) or lines[pos] != line[1:]:
                    raise ValueError('Patch context mismatch')
                pos += 1; old_count += 1
            if line[:1] in (' ', '+'):
                out.append(line[1:]); new_count += 1
            if line[:1] not in (' ', '+', '-'):
                raise ValueError('Unsupported patch line')
        if old_count != int(match[2] or 1) or new_count != int(match[4] or 1):
            raise ValueError('Patch hunk count mismatch')
    return ''.join(out + lines[pos:]).encode()


def apply(root, domain, target):
    root = Path(root).resolve()
    prepared = []
    for entry in load(MANIFEST)['patches']:
        if entry['domain'] != domain or target not in entry['targets']:
            continue
        path = root / safe_path(entry['path'])
        if not path.resolve().is_relative_to(root) or path.is_symlink():
            raise ValueError('Patch path escapes exported copy')
        patch = HOME / 'patches' / safe_path(entry['patch'])
        if filehash(patch) != entry['diff_sha256']:
            raise ValueError('Vendored diff hash mismatch')
        current = b'' if entry.get('new_file') and not path.exists() else path.read_bytes()
        backup = path.with_name(path.name + '.upstream')
        if digest(current) == entry['patched_sha256']:
            if not backup.is_file() or filehash(backup) != entry['upstream_sha256']:
                raise ValueError('Patched file lacks pristine backup')
            continue
        if digest(current) != entry['upstream_sha256']:
            raise ValueError(f'Upstream hash mismatch: {entry["path"]}')
        changed = patched_bytes(current, patch.read_text())
        if digest(changed) != entry['patched_sha256']:
            raise ValueError('Patched hash mismatch')
        prepared.append((path, backup, current, changed, patch))
    # Validate the entire set before changing anything.
    for path, backup, current, changed, patch in prepared:
        backup.write_bytes(current)
        path.with_name(path.name + '.patch').write_bytes(patch.read_bytes())
        path.write_bytes(changed)


def unpack(destination):
    manifest = load(MANIFEST)
    archive = HOME / manifest['uvm_archive']
    if filehash(archive) != manifest['uvm_archive_sha256']:
        raise ValueError('UVM archive hash mismatch')
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    with tarfile.open(archive) as stream:
        stream.extractall(destination, filter='data')
    matches = list(destination.rglob('src/uvm_pkg.sv'))
    if len(matches) != 1:
        raise ValueError('Unexpected UVM archive layout')
    return matches[0].parent.parent
