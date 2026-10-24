"""Retrieve the repository named by an explicit pinned target manifest."""
from pathlib import Path
import subprocess

from .evidence import ROOT


def fetch(config):
    destination = ROOT/config['vendor']
    if destination.exists():
        if not (destination/'.git').exists():
            raise ValueError('Destination exists without a Git checkout; leaving it unchanged')
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(['git', 'clone', '--', config['repository_url'], str(destination)], check=True)
        subprocess.run(['git', '-C', str(destination), 'checkout', '--detach', config['revision']], check=True)
    revision = subprocess.check_output(['git', '-C', str(destination), 'rev-parse', 'HEAD'], text=True).strip()
    dirty = subprocess.check_output(['git', '-C', str(destination), 'status', '--porcelain'], text=True).strip()
    if revision != config['revision'] or dirty:
        raise ValueError('Existing checkout is dirty or at a different revision; leaving it unchanged')
    print(f'FETCHED {destination} {revision}')
    return destination
