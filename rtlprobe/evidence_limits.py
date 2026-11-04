"""Capture-only per-file limit before exec; no target or provider selection."""
import argparse
import os
try:
    import resource
except ImportError:
    resource=None


def supported():
    return os.name == 'posix' and resource is not None and hasattr(resource, 'RLIMIT_FSIZE') and hasattr(os, 'execvp')


def exec_limited(command, byte_limit):
    if not supported():
        raise RuntimeError('capture requires enforced RLIMIT_FSIZE support')
    if type(byte_limit) is not int or not 1024 <= byte_limit <= 64*1024*1024:
        raise ValueError('capture per-file byte limit must be between 1 KiB and 64 MiB')
    if not command or any(not isinstance(value,str) or not value for value in command):
        raise ValueError('explicit execution argument list required')
    current=resource.getrlimit(resource.RLIMIT_FSIZE)
    if current[1] != resource.RLIM_INFINITY and current[1] < byte_limit:
        byte_limit=current[1]
    resource.setrlimit(resource.RLIMIT_FSIZE,(byte_limit,byte_limit))
    os.execvp(command[0],command)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bytes',required=True,type=int)
    parser.add_argument('command',nargs=argparse.REMAINDER)
    args=parser.parse_args()
    command=args.command[1:] if args.command[:1]==['--'] else args.command
    exec_limited(command,args.bytes)


if __name__=='__main__':main()
