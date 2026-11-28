"""Linux case-command supervision. Invoked as an isolated Python helper by Runner."""
from contextlib import contextmanager
import ctypes
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import signal
import socket
import subprocess
import sys


def exit_receipt(directory):
    """Read positive, command-bound evidence. Absence never establishes exit."""
    start = directory/'started.json'
    receipt = directory/'tree-exited.json'
    if start.is_symlink() or receipt.is_symlink() or not receipt.is_file():
        raise ValueError('Missing or unsafe process-tree exit receipt')
    with start.open('rb') as bound_start:
        fcntl.flock(bound_start, fcntl.LOCK_SH | fcntl.LOCK_NB)
        start_bytes = bound_start.read()
        commitment = json.loads(start_bytes).get('tree_launch_id')
        raw = receipt.read_bytes()
        value = json.loads(raw)
    if (not isinstance(value, dict) or value.get('schema') != 'rtlprobe-subreaper-exit-1'
            or value.get('command_directory') != str(directory.resolve())
            or value.get('start_sha256') != hashlib.sha256(start_bytes).hexdigest()
            or type(value.get('returncode')) is not int
            or not isinstance(value.get('exit_key'), str)
            or not re.fullmatch('[0-9a-f]{64}', value['exit_key'])
            or hashlib.sha256(bytes.fromhex(value['exit_key'])).hexdigest() != commitment):
        raise ValueError('Process-tree exit receipt does not match command')
    return value['returncode'], hashlib.sha256(raw).hexdigest()


@contextmanager
def launch(directory, command, cwd, stdout, stderr, env, memory, exit_key, timeout):
    reader, sender = socket.socketpair()
    with reader, sender:
        # Queue the private preimage before starting the supervisor. The native
        # worker receives neither this descriptor nor the key in its environment.
        reader.settimeout(timeout)
        reader.sendall(exit_key)
        reader.shutdown(socket.SHUT_WR)
        proc = subprocess.Popen(
            [sys.executable, '-I', '-S', '-B', str(Path(__file__).resolve()),
             str(directory.resolve()), str(sender.fileno()), str(memory or 0), *command],
            cwd=cwd, stdout=stdout, stderr=stderr, env=env, start_new_session=True,
            pass_fds=(sender.fileno(),))
        sender.close()
        try:
            with reader.makefile("rb") as stream:
                raw = stream.read(256)
            if not raw:
                raise OSError('Supervisor exited before worker registration')
            notice = json.loads(raw)
            if 'errno' in notice:
                proc.wait()
                raise OSError(notice['errno'], os.strerror(notice['errno']), command[0])
            yield proc, {'pid': notice['pid'], 'group_id': proc.pid}
        finally:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()


def supervise(directory, notify_fd, memory, command):
    # Linux reparents orphaned descendants, including new sessions, to the nearest
    # living subreaper. Register before the only fork that can launch native work.
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
        raise OSError(ctypes.get_errno(), 'Cannot supervise command descendants')
    signal.signal(signal.SIGCHLD, signal.SIG_DFL)
    with (directory/'started.json').open('rb') as bound_start:
        fcntl.flock(bound_start, fcntl.LOCK_EX)
        observe(directory, bound_start.read(), notify_fd, memory, command)


def observe(directory, start, notify_fd, memory, command):
    with os.fdopen(notify_fd, 'rb', closefd=False) as channel:
        key = channel.read(33)
    record = json.loads(start)
    if (len(key) != 32 or hashlib.sha256(key).hexdigest() != record.get('tree_launch_id')
            or record['command'] != command):
        raise ValueError('Supervised command differs from launch record')

    watched = {signal.SIGCHLD, signal.SIGTERM}
    original_mask = signal.pthread_sigmask(signal.SIG_BLOCK, watched)

    def restore_worker_limits():
        signal.pthread_sigmask(signal.SIG_SETMASK, original_mask)
        if memory:
            resource.setrlimit(resource.RLIMIT_AS, (memory, memory))

    with os.fdopen(notify_fd, 'wb', buffering=0) as notify:
        try:
            worker = subprocess.Popen(command, preexec_fn=restore_worker_limits)
        except OSError as exc:
            notice = {'errno': exc.errno}
            worker = None
        else:
            notice = {'pid': worker.pid}
        try:
            notify.write(json.dumps(notice).encode())
        except BrokenPipeError:
            pass  # The controller died. Its descendants still need independent observation.

    rc = reap_tree(worker, watched) if worker is not None else 127
    value = dict(schema='rtlprobe-subreaper-exit-1', command_directory=str(directory),
                 start_sha256=hashlib.sha256(start).hexdigest(), exit_key=key.hex(), returncode=rc)
    temp = directory/'tree-exited.tmp'
    with temp.open('x') as stream:
        json.dump(value, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    temp.replace(directory/'tree-exited.json')
    fd = os.open(directory, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def reap_tree(worker, watched):
    """Reap even reparented/clone children. Only this thread can release their PIDs."""
    cancelled = False
    while True:
        try:
            pid, status = os.waitpid(-1, os.WNOHANG | 0x40000000)  # Linux __WALL
        except ChildProcessError:
            if worker.returncode is None:
                raise RuntimeError('Native worker exit was not observed')
            return worker.returncode
        if pid:
            if pid == worker.pid:
                worker.returncode = os.waitstatus_to_exitcode(status)
            continue
        if cancelled:
            # Only signal our direct, unreaped children. Orphans are adopted
            # here as their parents exit, even if they started new sessions.
            for child in Path('/proc/thread-self/children').read_text().split():
                try:
                    os.kill(int(child), signal.SIGKILL)
                except ProcessLookupError:
                    pass
            signal.sigtimedwait(watched, 0.02)
        else:
            cancelled = signal.sigwait(watched) == signal.SIGTERM


if __name__ == '__main__':
    supervise(Path(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]), sys.argv[4:])
