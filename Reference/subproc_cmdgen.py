# subprocess
 
import os
import argparse
import shlex
import subprocess
from pathlib import Path


def main():
    """ 20251010 MMH subproc_cmdgen
        Given a command to launch as a subprocess convert it 
        to a list of arguments suitable for passing to subprocess.Popen.
        Args:
            cmd (str): Command line to run (in quotes).
        Returns:
            List[str]: List of arguments for subprocess.
    """

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
    return proc_args
    # try:
    #     subprocess.run(proc_args, stdin=None, input=None, stdout=None, stderr=None, 
    #                   capture_output=False, shell=False, cwd=str(project_root), timeout=None,
    #                   check=Trie, encoding=None, errors=None, text=None, env=None, 
    #                   universal_newlines=None),     # **other_popen_kwargs)
    # except subprocess.CalledProcessError as e:
    #     print(f"Error executing command: {e}")
     

if __name__ == "__main__" :
    main()

