"""Wait for Windows Job Object assignment before starting the requested command."""

import subprocess
import sys


def main():
    if sys.stdin.buffer.readline() != b"go\n":
        return 1
    return subprocess.call(sys.argv[1:], stdin=subprocess.DEVNULL)


if __name__ == "__main__":
    raise SystemExit(main())
