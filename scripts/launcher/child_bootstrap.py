"""Wait for Windows Job Object assignment before starting the requested command."""

import subprocess
import sys
import os


def main(*, pass_stdin=False, arguments=None, gate_handle=None):
    descriptor = sys.stdin.fileno()
    if gate_handle is not None:
        import msvcrt
        descriptor = msvcrt.open_osfhandle(gate_handle, os.O_RDONLY | os.O_BINARY)
    allowed = os.read(descriptor, 3) == b'go\n'
    if gate_handle is not None:
        os.close(descriptor)
    if not allowed:
        return 1
    return subprocess.call(sys.argv[1:] if arguments is None else arguments,
                           stdin=sys.stdin if pass_stdin else subprocess.DEVNULL)


if __name__ == "__main__":
    pipe = sys.argv[1:2] == ['--gate-handle']
    raise SystemExit(main(pass_stdin=pipe, arguments=sys.argv[3:] if pipe else None,
                         gate_handle=int(sys.argv[2]) if pipe else None))
