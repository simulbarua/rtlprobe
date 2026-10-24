"""Bounded commands and hashed, atomic evidence records."""

import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import shutil
import signal
import subprocess
import sys
import time
import fcntl
from contextlib import contextmanager
from datetime import datetime, timezone
from importlib.metadata import version

CODE_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("RTLPROBE_DATA_ROOT", str(CODE_ROOT))).expanduser().resolve()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def filehash(path):
    return digest(Path(path).read_bytes())


def identity(value):
    return digest(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w") as stream:
        stream.write(json.dumps(value, indent=2, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    tmp.replace(path)


def write_once(path, value):
    """Idempotent publication under workspace_lock; never replace a changed record."""
    path = Path(path)
    if path.exists():
        if load(path) != value:
            raise ValueError(f"Refusing to overwrite immutable record: {path}")
        return
    save(path, value)


@contextmanager
def workspace_lock(root=ROOT):
    path = Path(root)/"data/state/controller.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Another qualification/mutation controller is active") from None
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


class CommandError(RuntimeError):
    def __init__(self, record):
        self.record = record
        super().__init__(f"Command failed: {record['id']} (exit {record['returncode']})")


def load(path):
    return json.loads(Path(path).read_text())


def treehashes(path):
    return {str(p.relative_to(path)): filehash(p) for p in sorted(Path(path).rglob("*")) if p.is_file()}


def manifest(path):
    save(Path(path)/"manifest.json", {"schema_version": "pilot-1", "files": {
        k: v for k, v in treehashes(path).items() if k != "manifest.json"}})


def verify_manifest(path):
    path = Path(path)
    expected = load(path/"manifest.json")["files"]
    actual = {k: v for k, v in treehashes(path).items() if k != "manifest.json"}
    if expected != actual:
        raise ValueError("Artifact manifest mismatch (missing, changed, or additional files)")


def environment():
    commands = {"iverilog": ["-V"], "vvp": ["-V"], "yosys": ["-V"],
                "verilator": ["--version"], "git": ["--version"], "patch": ["--version"]}
    tools = {}
    for name, args in commands.items():
        exe = shutil.which(name)
        if not exe:
            raise RuntimeError(f"Missing required tool: {name}")
        result = subprocess.run([exe, *args], capture_output=True, text=True, timeout=15)
        output = result.stdout + result.stderr
        tools[name] = {"executable": str(Path(exe).resolve()), "sha256": filehash(exe),
                       "version": output.strip(), "version_exit_code": result.returncode}
    return {"platform": platform.platform(), "machine": platform.machine(),
            "python": sys.version, "python_executable": str(Path(sys.executable).resolve()),
            "python_sha256": filehash(sys.executable),
            "packages": {p: version(p) for p in ("pyverilog", "ply", "jsonschema")},
            "tools": tools, "locale": "C", "timezone": "UTC"}


class Runner:
    def __init__(self, out, limits):
        self.out = Path(out)
        self.out.mkdir(parents=True, exist_ok=True)
        self.limits = limits
        self.started = time.monotonic()
        self.cpu_start = resource.getrusage(resource.RUSAGE_CHILDREN)
        self.records = []

    def run(self, name, command, cwd, timeout):
        elapsed = time.monotonic() - self.started
        cpu = resource.getrusage(resource.RUSAGE_CHILDREN)
        used_cpu = cpu.ru_utime + cpu.ru_stime - self.cpu_start.ru_utime - self.cpu_start.ru_stime
        if elapsed >= self.limits["campaign_seconds"] or used_cpu >= self.limits["cpu_seconds"]:
            raise RuntimeError("Campaign resource budget exhausted")
        used_disk = sum(p.stat().st_size for p in self.out.rglob("*") if p.is_file())
        if used_disk >= self.limits["disk_bytes"]:
            raise RuntimeError("Campaign disk budget exhausted")
        limit = min(timeout, self.limits["campaign_seconds"] - elapsed)
        directory = self.out/"commands"/name
        directory.mkdir(parents=True, exist_ok=False)
        command = [str(x) for x in command]
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LC_ALL": "C", "TZ": "UTC"}
        start = time.monotonic()
        started_at = datetime.now(timezone.utc).isoformat()
        before = resource.getrusage(resource.RUSAGE_CHILDREN)
        save(directory/"started.json", {"id": name, "command": command, "cwd": str(cwd),
                                       "started_at": started_at, "timeout_seconds": limit})
        # Each command is its own process group, so timeouts terminate tool children too.
        with (directory/"stdout.log").open("wb") as stdout, (directory/"stderr.log").open("wb") as stderr:
            proc = subprocess.Popen(command, cwd=cwd, stdout=stdout, stderr=stderr,
                                    env=env, start_new_session=True)
            save(directory/"process.json", {"pid": proc.pid})
            timed_out = False
            interrupted = False
            try:
                rc = proc.wait(timeout=limit)
            except subprocess.TimeoutExpired:
                timed_out = True
                os.killpg(proc.pid, signal.SIGKILL)
                rc = proc.wait()
            except BaseException:
                interrupted = True
                if proc.poll() is None:
                    os.killpg(proc.pid, signal.SIGKILL)
                rc = proc.wait()
        after = resource.getrusage(resource.RUSAGE_CHILDREN)
        record = {"id": name, "command": command, "cwd": str(cwd), "started_at": started_at,
                  "returncode": rc, "timed_out": timed_out, "timeout_seconds": limit,
                  "elapsed_seconds": time.monotonic()-start,
                  "cpu_seconds": after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime,
                  "stdout": str((directory/"stdout.log").relative_to(self.out)),
                  "stderr": str((directory/"stderr.log").relative_to(self.out)),
                  "stdout_sha256": filehash(directory/"stdout.log"),
                  "stderr_sha256": filehash(directory/"stderr.log")}
        record["interrupted"] = interrupted
        save(directory/"run.json", record)
        self.records.append(record)
        save(self.out/"commands.json", self.records)
        if interrupted:
            raise KeyboardInterrupt("Command interrupted; logs and process outcome preserved")
        return record

    def require(self, name, command, cwd, timeout):
        record = self.run(name, command, cwd, timeout)
        if record["returncode"] or record["timed_out"]:
            raise CommandError(record)
        return record
