#!/usr/bin/env python3
"""
Regenerate the catalogue outputs, then run Looper's one-way mirror script.

AGENTS.md steps 4 to 6 follow every change to the registry: regenerate the
guide and summary, rebuild the dashboard, and mirror the validated semantic
files into the Looper vault. `merge_member_list.py` calls this module after it
changes the registry, so a new roster reaches the vault without a person
remembering the last step.

The mirror script belongs to Looper, not to this repository, so this module
holds no vault path and copies no file itself. Set LOOPER_MIRROR_CMD to the
full command that runs the mirror, for example:

    export LOOPER_MIRROR_CMD="python3 /path/to/looper/mirror_catalogue.py"

The command runs from the repository root. It runs only after validation
passes, so the vault never receives a file that failed the checks. When the
variable is not set, this module says so and mirrors nothing; it never guesses
a target, because the vault copies must not be edited by hand.

Usage:
    python3 SKILL/scripts/sync_looper.py [--no-build] [--require]

--no-build  skip the dashboard rebuild
--require   exit 1 when LOOPER_MIRROR_CMD is not set
"""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
MIRROR_ENV = "LOOPER_MIRROR_CMD"


def run(command: list[str]) -> None:
    print(f"$ {' '.join(command)}")
    try:
        subprocess.run(command, cwd=ROOT, check=True)
    except subprocess.CalledProcessError as error:
        # A failed check is the gate working. Stop with one line, not a traceback.
        raise SystemExit(f"ERROR: {' '.join(command)} exited {error.returncode}; nothing after it ran")


def refresh_and_mirror(build: bool = True, require: bool = False) -> bool:
    """Validate, rebuild, then mirror. Return True when the mirror ran."""
    python = sys.executable
    run([python, str(SCRIPTS / "validate_catalogue.py")])  # regenerates the guide and summary
    if build:
        run([python, str(SCRIPTS / "build_dashboard.py")])
    run([python, str(SCRIPTS / "validate_catalogue.py"), "--check"])  # the gate before the vault

    command = os.environ.get(MIRROR_ENV, "").strip()
    if not command:
        message = f"{MIRROR_ENV} is not set: the Looper mirror did NOT run. Run Looper's mirror script by hand."
        if require:
            raise SystemExit(f"ERROR: {message}")
        print(f"WARNING: {message}")
        return False
    run(shlex.split(command))
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-build", action="store_true", help="skip the dashboard rebuild")
    parser.add_argument("--require", action="store_true", help=f"fail when {MIRROR_ENV} is not set")
    args = parser.parse_args()
    refresh_and_mirror(build=not args.no_build, require=args.require)


if __name__ == "__main__":
    main()
