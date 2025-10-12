# subprocess.SubprocessError
# 20251010 MMH Given a command to launch as a subprocess convert it 
# to a list of arguments suitable for passing to subprocess.Popen.
 
import os
import argparse
import shlex
import subprocess
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        usage='%(prog)s [options]',
        description="Format a command line for use by subprocess.",
        add_help=True,
        exit_on_error=True
    )


    parser.add_argument("cmd", type=str, 
                        help="Command line to run (in quotes).")
    args = parser.parse_args()

    print(f"String passed in:\n{args.cmd}\n")

    project_root = Path(__file__).parents[1].resolve()
    print(f"Project Root:\n{project_root}\n")

    proc_args = shlex.split(args.cmd, posix=False) if os.name == "nt" else shlex.split(args.cmd)
    print(f"Process Arguments List:\n{proc_args}\n")

    p = subprocess.Popen(proc_args, cwd=str(project_root)) # Success!   

if __name__ == "__main__" :
    main()

