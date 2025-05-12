#!/usr/bin/env python3

from typing import Optional
import subprocess
import os
import time

MAX_CPU_PER_JOB = 8


def read_commit_hashes(target) -> list[str]:
    with open(f"./compare/{target}/compares", "r") as f:
        result = [line for line in f.read().splitlines()]
    return result


def serial_jobs_configure(
    cmds: list[tuple[list[str], Optional[str], bool]],
) -> tuple[int, Optional[str]]:
    for cmd, cwd, check in cmds:
        start = time.time()
        proc = subprocess.run(cmd, cwd=cwd, stdout=subprocess.DEVNULL)
        elapsed = time.time() - start

        if not check and proc.returncode:
            # Job exit with error, but ignorable
            pass
        elif check and proc.returncode:
            # Job exit with error, and pass to user
            return (proc.returncode, "".join(cmd) + "\n" + proc.stderr)
        else:
            # Job exit successfully
            pass

    return (proc.returncode, None)


def ir_build(target: str, chash: str) -> tuple[int, Optional[str]]:
    cleanup()
    return serial_jobs_configure(
        [
            (["git", "checkout", chash], CONFIG["LIBARCHIVE_DIRECTORY"], True),
            (
                # Neutralizing -Werrors. Caution!
                # find . -type f -exec sed -i 's/-Werror//g' {} +
                [
                    "find",
                    ".",
                    "-type",
                    "f",
                    "-exec",
                    "sed",
                    "-i",
                    "s/-Werror//g",
                    "{}",
                    "+",
                ],
                CONFIG["LIBARCHIVE_DIRECTORY"],
                True,
            ),
            (
                [
                    "awk",
                    f'{{ print >> "{CONFIG["LIBARCHIVE_DIRECTORY"] + "/libarchive/CMakeLists.txt"}" }}',
                    "mod_cmakelists.txt",
                ],
                CONFIG["CFGDIFF_IRCONV_DIRECTORY"],
                True,
            ),
            (
                ["cmake", "."],
                CONFIG["LIBARCHIVE_DIRECTORY"],
                True,
            ),
            (
                ["make"],
                CONFIG["LIBARCHIVE_DIRECTORY"],
                True,
            ),
        ]
    )


def make_cfg(target: str, chash: str) -> tuple[int, Optional[str]]:
    return serial_jobs_configure(
        [
            (
                [
                    "find",
                    ".",
                    "-type",
                    "f",
                    "-name",
                    "*.bc",
                    "-exec",
                    "opt",
                    "-passes=dot-cfg",
                    "-disable-output",
                    "{}",
                    ";",
                ],
                CONFIG["BUILD_OUTPUT_DIRECTORY"] + f"/{target}/libarchive-bcs-{chash}",
                True,
            ),  # Convert to CFG
            (
                ["find", ".", "-type", "f", "-name", "*.bc", "-delete"],
                CONFIG["BUILD_OUTPUT_DIRECTORY"] + f"/{target}/libarchive-bcs-{chash}",
                True,
            ),  # Remove all bitcodes
            (
                [
                    "find",
                    ".",
                    "-type",
                    "f",
                    "-name",
                    "'.*'",
                    "-exec",
                    "rename",
                    "'s|/\.([^/]*)$|/\\1|'",
                    "{}",
                    "+",
                ],
                CONFIG["BUILD_OUTPUT_DIRECTORY"] + f"/{target}/libarchive-bcs-{chash}",
                True,
            ),  # Remove all un-normalized CFGs
        ]
    )


def cleanup():
    return serial_jobs_configure(
        [
            (["git", "clean", "-fd"], CONFIG["LIBARCHIVE_DIRECTORY"], True),
            (["git", "reset", "--hard"], CONFIG["LIBARCHIVE_DIRECTORY"], True),
        ]
    )


if __name__ == "__main__":

    with open(".setup", "r") as setup:
        CONFIG = {
            line.split()[0].strip(): line.split()[-1].strip()
            for line in setup.readlines()
        }

    for key in CONFIG:
        os.environ[key] = CONFIG[key]

    target_name = "libarchive"

    commit_hashes = read_commit_hashes(target_name)

    serial_jobs_configure(
        [(["mkdir", f"{target_name}"], CONFIG["BUILD_OUTPUT_DIRECTORY"], False)]
    )

    for commit in commit_hashes:
        print("IR BUILDING")
        ir_build(target_name, commit)
        print("CFG BUILDING")
        make_cfg(target_name, commit)
