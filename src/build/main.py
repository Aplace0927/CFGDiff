#!/usr/bin/env python3

from typing import Optional
import subprocess
import os
import logging
import time

MAX_CPU_PER_JOB = 8


def read_commit_hashes() -> list[tuple[str, str]]:
    with open("compares", "r") as f:
        result = [line for line in f.read().splitlines()]
    return result[0], result[1:]


def serial_jobs_configure(
    cmds: list[tuple[list[str], Optional[str], bool]],
) -> tuple[int, Optional[str]]:
    for cmd, cwd, check in cmds:
        start = time.time()
        proc = subprocess.run(cmd, cwd=cwd, stdout=subprocess.DEVNULL)
        elapsed = time.time() - start

        if not check and proc.returncode:
            # discord.add_message_to_last_field(f"* :warning: `{' '.join(cmd)}` *returned {proc.returncode}* ({elapsed:.2f} s)")
            pass
        elif check and proc.returncode:
            # logging.log(logging.ERROR, f"[{' '.join(cmd)}] @ {cwd} returns {proc.returncode}")
            return (proc.returncode, "".join(cmd) + "\n" + proc.stderr)
        else:
            # logging.log(logging.WARN, f"[{' '.join(cmd)}] @ {cwd} exits successfully")
            # discord.add_message_to_last_field(f"* :white_check_mark: `{' '.join(cmd)}` ({elapsed:.2f} s)")
            pass

    return (proc.returncode, None)


def ir_build(target: str, chash: str) -> tuple[int, Optional[str]]:
    # logging.log(logging.WARN, f"Start building CHASH={chash}")
    cleanup()
    # discord.add_field(f":information_source: Generating LLVM BC of `{chash}`")
    return serial_jobs_configure(
        [
            (["git", "checkout", chash], CONFIG["OPENSSL_GIT_DIRECTORY"], True),
            (
                ["cp", "build_bitcode.sh", CONFIG["OPENSSL_GIT_DIRECTORY"]],
                CONFIG["CFGDIFF_IRCONV_DIRECTORY"],
                True,
            ),
            (
                ["cp", "comp_db_generate.py", CONFIG["OPENSSL_GIT_DIRECTORY"]],
                CONFIG["CFGDIFF_IRCONV_DIRECTORY"],
                True,
            ),
            (["/bin/bash", "build_bitcode.sh"], CONFIG["OPENSSL_GIT_DIRECTORY"], True),
            (
                [
                    "mv",
                    f"./bcs",
                    CONFIG["BUILD_OUTPUT_DIRECTORY"] + f"/{target}/openssl-bcs-{chash}",
                ],
                CONFIG["OPENSSL_GIT_DIRECTORY"],
                True,
            ),
        ]
    )


def make_cfg(target: str, chash: str) -> tuple[int, Optional[str]]:
    return serial_jobs_configure(
        [
            (
                ["find", ".", "-type", "f", "-name", "*-lib-*", "-delete"],
                CONFIG["BUILD_OUTPUT_DIRECTORY"] + f"/{target}/openssl-bcs-{chash}",
                True,
            ),  # Remove all libraries (except shared library output)
            (
                [
                    "find",
                    ".",
                    "-type",
                    "f",
                    "-exec",
                    "opt",
                    "-passes=dot-cfg",
                    "-disable-output",
                    "{}",
                    ";",
                ],
                CONFIG["BUILD_OUTPUT_DIRECTORY"] + f"/{target}/openssl-bcs-{chash}",
                True,
            ),  # Convert to CFG
            (
                ["find", ".", "-type", "f", "-name", "*.bc", "-delete"],
                CONFIG["BUILD_OUTPUT_DIRECTORY"] + f"/{target}/openssl-bcs-{chash}",
                True,
            ),  # Remove all bitcodes
            (
                ["find", ".", "-type", "f", "-name", "'.*'", "-delete"],
                CONFIG["BUILD_OUTPUT_DIRECTORY"] + f"/{target}/openssl-bcs-{chash}",
                True,
            ),  # Remove all un-normalized CFGs
        ]
    )


def cleanup():
    return serial_jobs_configure(
        [
            (["git", "clean", "-fd"], CONFIG["OPENSSL_GIT_DIRECTORY"], True),
            (["git", "reset", "--hard"], CONFIG["OPENSSL_GIT_DIRECTORY"], True),
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

    commit_hash_pairs = read_commit_hashes()

    target_name, commits = commit_hash_pairs

    print(f"{target_name} for {commits}.")
    serial_jobs_configure(
        [(["mkdir", f"{target_name}"], CONFIG["BUILD_OUTPUT_DIRECTORY"], False)]
    )

    for commit in commits:
        ir_build(target_name, commit)
        make_cfg(target_name, commit)

        # webhook_send.success_webhook([f"Success Diff {vulnerable} {patched}"])
