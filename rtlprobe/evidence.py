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
from . import command_tree
from . import measurement

from contextlib import contextmanager, nullcontext
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


def save_bytes(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    tmp.replace(path)


def save(path, value):
    save_bytes(path, (json.dumps(value, indent=2, sort_keys=True) + "\n").encode())


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
        with measurement.span('workspace.lock.acquire', 'locks'):
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


def require_execution_guard(execution_guard):
    if execution_guard is not None and (not callable(execution_guard) or execution_guard() is not True):
        raise ValueError('External execution readiness guard refused command progress')


def checks_command_boundaries(guard):
    """Opt in only when both command hooks run the full readiness check."""
    return (getattr(guard, 'checks_command_boundaries', False) is True
            and callable(getattr(guard, 'before_command', None))
            and callable(getattr(guard, 'after_command', None)))


def begin_command(guard, name, command, cwd, timeout):
    if not checks_command_boundaries(guard):
        require_execution_guard(guard)
    if guard is not None and hasattr(guard, 'before_command'):
        allowed = guard.before_command(name, [str(x) for x in command], str(Path(cwd or Path.cwd())), timeout)
        if allowed is True:
            return timeout
        if type(allowed) not in (int, float) or not 0 < allowed or (timeout is not None and allowed > timeout):
            raise ValueError('Scoped command authorization refused')
        return allowed
    return timeout


def end_command(guard, record):
    if guard is not None and hasattr(guard, 'after_command'):
        if guard.after_command(record) is not True:
            raise ValueError('Scoped command accounting refused')
    if not checks_command_boundaries(guard):
        require_execution_guard(guard)


def environment(*, execution_guard=None):
    commands = {"iverilog": ["-V"], "vvp": ["-V"], "yosys": ["-V"],
                "verilator": ["--version"], "git": ["--version"], "patch": ["--version"]}
    tools = {}
    for name, args in commands.items():
        if not checks_command_boundaries(execution_guard):
            require_execution_guard(execution_guard)
        exe = shutil.which(name)
        if not exe:
            raise RuntimeError(f"Missing required tool: {name}")
        timeout = begin_command(execution_guard, 'version_'+name, [exe, *args], None, 15)
        result = subprocess.run([exe, *args], capture_output=True, text=True, timeout=timeout)
        end_command(execution_guard, {'id': 'version_'+name, 'returncode': result.returncode,
                                      'timed_out': False, 'interrupted': False})
        output = result.stdout + result.stderr
        tools[name] = {"executable": str(Path(exe).resolve()), "sha256": filehash(exe),
                       "version": output.strip(), "version_exit_code": result.returncode}
    return {"platform": platform.platform(), "machine": platform.machine(),
            "python": sys.version, "python_executable": str(Path(sys.executable).resolve()),
            "python_sha256": filehash(sys.executable),
            "packages": {p: version(p) for p in ("pyverilog", "ply", "jsonschema")},
            "tools": tools, "locale": "C", "timezone": "UTC"}


def _stop_group(proc, supervised):
    if proc.poll() is None:
        try:
            if supervised:
                # Let the subreaper outlive ordinary termination and finish its receipt.
                proc.terminate()
                try:
                    return proc.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    pass
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    return proc.wait()


class Runner:
    def __init__(self, out, limits, *, execution_guard=None, supervise_tree=False):
        self.supervise_tree = supervise_tree and sys.platform == "linux"
        self.execution_guard = execution_guard
        self.guard()
        self.out = Path(out)
        self.out.mkdir(parents=True, exist_ok=True)
        self.limits = limits
        self.started = time.monotonic()
        self.cpu_start = resource.getrusage(resource.RUSAGE_CHILDREN)
        self.records = []

    def guard(self):
        require_execution_guard(self.execution_guard)

    def run(self, name, command, cwd, timeout, *, env_extra=None):
        self.guard()
        elapsed = time.monotonic() - self.started
        cpu = resource.getrusage(resource.RUSAGE_CHILDREN)
        used_cpu = cpu.ru_utime + cpu.ru_stime - self.cpu_start.ru_utime - self.cpu_start.ru_stime
        wall, cpu_limit = self.limits["campaign_seconds"], self.limits["cpu_seconds"]
        if (wall is not None and elapsed >= wall) or (cpu_limit is not None and used_cpu >= cpu_limit):
            raise RuntimeError("Campaign resource budget exhausted")
        used_disk = sum(p.stat().st_size for p in self.out.rglob("*") if p.is_file())
        if used_disk >= self.limits["disk_bytes"]:
            raise RuntimeError("Campaign disk budget exhausted")
        limit = min((n for n in (timeout, wall-elapsed if wall is not None else None) if n is not None), default=None)
        directory = self.out/"commands"/name
        directory.mkdir(parents=True, exist_ok=False)
        command = [str(x) for x in command]
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LC_ALL": "C", "TZ": "UTC"}
        if env_extra:
            if set(env_extra) - {'SDKROOT', 'CC', 'CXX', 'PYTHONDONTWRITEBYTECODE'}:
                raise ValueError('Unsupported build environment key')
            env.update(env_extra)
        # Each command is its own process group, so timeouts terminate tool children too.
        memory = self.limits.get('memory_bytes')
        memory_supported = sys.platform.startswith('linux') and hasattr(resource, 'RLIMIT_AS')
        def limit_memory():
            resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
        with (directory/"stdout.log").open("wb") as stdout, (directory/"stderr.log").open("wb") as stderr:
            limit = begin_command(self.execution_guard, name, command, cwd, limit)
            with measurement.span(name, measurement.command_category(name), output_bytes_before=used_disk):
                # The command budget starts after its execution checks return.
                start = time.monotonic()
                started_at = datetime.now(timezone.utc).isoformat()
                before = resource.getrusage(resource.RUSAGE_CHILDREN)
                start_record = {"id": name, "command": command, "cwd": str(cwd),
                                "started_at": started_at, "timeout_seconds": limit}
                if self.supervise_tree:
                    exit_key = os.urandom(32)
                    start_record["tree_launch_id"] = digest(exit_key)
                save(directory/"started.json", start_record)
                if self.supervise_tree:
                    child = command_tree.launch(directory, command, cwd, stdout, stderr, env, memory, exit_key, limit)
                else:
                    proc = subprocess.Popen(command, cwd=cwd, stdout=stdout, stderr=stderr,
                                            env=env, start_new_session=True,
                                            preexec_fn=limit_memory if memory and memory_supported else None)
                    child = nullcontext((proc, {"pid": proc.pid}))
                with child as (proc, process_record):
                    try:
                        save(directory/"process.json", process_record)
                    except BaseException:
                        _stop_group(proc, self.supervise_tree)
                        raise
                    timed_out = False
                    interrupted = False
                    try:
                        wait_limit = max(0, limit - (time.monotonic() - start)) if self.supervise_tree and limit is not None else limit
                        rc = proc.wait(timeout=wait_limit)
                    except subprocess.TimeoutExpired:
                        timed_out = True
                    except BaseException:
                        interrupted = True
                    if timed_out or interrupted:
                        rc = _stop_group(proc, self.supervise_tree)
                    if self.supervise_tree:
                        # Without a positive observation, leave the attempt unfinished.
                        if rc != 0:
                            raise OSError("Process-tree supervisor lost before durable exit evidence")
                        try:
                            rc, _ = command_tree.exit_receipt(directory)
                        except (OSError, ValueError) as exc:
                            raise OSError("Invalid process-tree exit evidence") from exc
        after = resource.getrusage(resource.RUSAGE_CHILDREN)
        record = {"id": name, "command": command, "cwd": str(cwd), "started_at": started_at,
                  "returncode": rc, "timed_out": timed_out, "timeout_seconds": limit,
                  "elapsed_seconds": time.monotonic()-start,
                  "cpu_seconds": after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime,
                  "stdout": str((directory/"stdout.log").relative_to(self.out)),
                  "stderr": str((directory/"stderr.log").relative_to(self.out)),
                  "stdout_sha256": filehash(directory/"stdout.log"),
                  "stderr_sha256": filehash(directory/"stderr.log")}
        if memory is not None:
            record['memory_limit'] = {'bytes': memory, 'enforced': memory_supported,
                                      'scope': 'per-process virtual address space' if memory_supported else 'unavailable on this host'}
        record["interrupted"] = interrupted
        save(directory/"run.json", record)
        self.records.append(record)
        save(self.out/"commands.json", self.records)
        end_command(self.execution_guard, record)
        if interrupted:
            raise KeyboardInterrupt("Command interrupted; logs and process outcome preserved")
        if not checks_command_boundaries(self.execution_guard):
            self.guard()
        return record

    def require(self, name, command, cwd, timeout, *, env_extra=None):
        record = self.run(name, command, cwd, timeout, env_extra=env_extra)
        if record["returncode"] or record["timed_out"]:
            raise CommandError(record)
        return record
