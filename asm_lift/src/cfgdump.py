#!/usr/bin/env python3

from typing import Optional
import subprocess
import os
import logging
from webhook import webhook_send

MAX_CPU_PER_JOB = 8

WEBHOOK_URL = r"https://discord.com/api/webhooks/1332309988210905239/ERFT7rZVeg1hkihLAhi99InqaQ0Mc3KnNhAIiHB3TKA3u6AVuKiGHeRshRXgnoyO_INj"

def read_commit_hashes() -> list[tuple[str, str]]:
    with open("compares", "r") as f:
        result = [(line.split()[0], line.split()[-1]) for line in f.read().splitlines()]
    return result

def serial_jobs_configure(discord: webhook_send.DiscordWebhookLogger, cmds: list[tuple[list[str], Optional[str], bool]]) -> tuple[int, Optional[str]]:
    for cmd, cwd, check in cmds:
        proc = subprocess.run(cmd, cwd=cwd, stdout=subprocess.DEVNULL)
        if not check and proc.returncode:
            discord.add_message_to_last_field(f"* :warning: `{' '.join(cmd)}` *returned {proc.returncode}*")
        elif check and proc.returncode:
            # logging.log(logging.ERROR, f"[{' '.join(cmd)}] @ {cwd} returns {proc.returncode}")
            discord.add_message_to_last_field(f"* :x: `{' '.join(cmd)}` **returned {proc.returncode}**")
            discord.embed.add_embed_field(name="Error Message", value=proc.stderr, inline=False)
            discord.change_status(webhook_send.DiscordWebhookLogger.WebhookLogStatus.FAIL)
            return (proc.returncode, "".join(cmd) + "\n" + proc.stderr)
        # logging.log(logging.WARN, f"[{' '.join(cmd)}] @ {cwd} exits successfully")
        else:
            discord.add_message_to_last_field(f"* :white_check_mark: `{' '.join(cmd)}`")
    
    return (proc.returncode, None)

def build(discord: webhook_send.DiscordWebhookLogger, chash: str) -> tuple[int, Optional[str]]:
    # logging.log(logging.WARN, f"Start building CHASH={chash}")
    cleanup(discord)
    discord.add_field(f":information_source: Start building `{chash}`")
    return serial_jobs_configure(discord,
            [
                (["git", "checkout", chash], CONFIG["OPENSSL_GIT_DIRECTORY"], True),

                (["make", "clean"], CONFIG["OPENSSL_GIT_DIRECTORY"], False),
                (["make", "clean"], CONFIG["OPENSSL_GIT_DIRECTORY"], False),

                (["make", "depend"], CONFIG["OPENSSL_GIT_DIRECTORY"], True),
                (["make", "all", f"-j{MAX_CPU_PER_JOB}"], CONFIG["OPENSSL_GIT_DIRECTORY"], True),

                (["mv", "./libcrypto.so.3", CONFIG["BUILD_OUTPUT_DIRECTORY"] + f"/libcrypto_{chash}"], CONFIG["OPENSSL_GIT_DIRECTORY"], True),
                (["mv", "./libssl.so.3", CONFIG["BUILD_OUTPUT_DIRECTORY"] + f"/libssl_{chash}"], CONFIG["OPENSSL_GIT_DIRECTORY"], True),
            ]
        )

def cleanup(discord: webhook_send.DiscordWebhookLogger):
    discord.add_field(f":broom: Cleaning up building environment")
    return serial_jobs_configure(discord,
            [
                (["git", "reset", "--hard"], CONFIG["OPENSSL_GIT_DIRECTORY"], True),
                (["./Configure", "linux-x86_64-clang"], CONFIG["OPENSSL_GIT_DIRECTORY"], True),
            ]
        )

def get_libcrypto_diff(discord: webhook_send.DiscordWebhookLogger, vuln_chash: str, patched_chash: str):
    # logging.log(logging.WARN, f"Getting `libcrypto` diff between VHASH={vuln_chash} and PHASH={patched_chash}")
    discord.add_field(f":arrows_clockwise: :lock: Diffing libcrypto: `{vuln_chash}` `{patched_chash}`")
    return serial_jobs_configure(discord, [
        (["./main.py", CONFIG["BUILD_OUTPUT_DIRECTORY"] + f"/libcrypto_{vuln_chash}", CONFIG["BUILD_OUTPUT_DIRECTORY"] + f"/libcrypto_{patched_chash}"], CONFIG["CFGDIFF_ASMLIFT_DIRECTORY"], True),
        (["mv", f"./cfgdiff_libcrypto_{vuln_chash}_libcrypto_{patched_chash}.diff", CONFIG["DIFF_OUTPUT_DIRECTORY"]], CONFIG["CFGDIFF_ASMLIFT_DIRECTORY"], True),
    ])

def get_libssl_diff(discord: webhook_send.DiscordWebhookLogger, vuln_chash: str, patched_chash: str):
    # logging.log(logging.WARN, f"Getting `libssl` diff between VHASH={vuln_chash} and PHASH={patched_chash}")
    discord.add_field(f":arrows_clockwise: :wireless: Diffing libssl: `{vuln_chash}` `{patched_chash}`")
    return serial_jobs_configure(discord, [
        (["./main.py", CONFIG["BUILD_OUTPUT_DIRECTORY"] + f"/libssl_{vuln_chash}", CONFIG["BUILD_OUTPUT_DIRECTORY"] + f"/libssl_{patched_chash}"], CONFIG["CFGDIFF_ASMLIFT_DIRECTORY"], True),
        (["mv", f"./cfgdiff_libssl_{vuln_chash}_libssl_{patched_chash}.diff", CONFIG["DIFF_OUTPUT_DIRECTORY"]], CONFIG["CFGDIFF_ASMLIFT_DIRECTORY"], True),
    ])

def bindiff(vuln_path: str, patched_path: str, cwd: str) -> bool:
    ret = subprocess.run(["diff", vuln_path, patched_path], cwd=cwd)
    if ret.returncode == 0:
        return False
    elif ret.returncode == 1:
        return True
    else:
        logging.log(logging.ERROR, " ".join(ret.args) + f" returned {ret.returncode}")
        raise Exception(ret.stderr)


if __name__ == "__main__":

    with open(".setup", "r") as setup:
        CONFIG = {line.split()[0].strip(): line.split()[-1].strip() for line in setup.readlines()}

    os.environ["CC"] = CONFIG["CC"]
    os.environ["CXX"] = CONFIG["CXX"]
    os.environ["LLVM_PROJECT_PATH"] = CONFIG["LLVM_PROJECT_PATH"]

    commit_hash_pairs = read_commit_hashes()

    for vulnerable, patched in commit_hash_pairs:
        discord = webhook_send.DiscordWebhookLogger(WEBHOOK_URL, "Building Status", f"Diffing `{vulnerable}` `{patched}`")
        
        build_vuln = build(discord, vulnerable)

        build_patch = build(discord, patched)

        if bindiff(f"./libcrypto_{vulnerable}", f"./libcrypto_{patched}", CONFIG["BUILD_OUTPUT_DIRECTORY"]):
            config_diff = get_libcrypto_diff(discord, vulnerable, patched)
        
        if bindiff(f"./libssl_{vulnerable}", f"./libssl_{patched}", CONFIG["BUILD_OUTPUT_DIRECTORY"]):
            config_diff = get_libssl_diff(discord, vulnerable, patched)
        
        discord.change_status(webhook_send.DiscordWebhookLogger.WebhookLogStatus.SUCCESS)
        # webhook_send.success_webhook([f"Success Diff {vulnerable} {patched}"])