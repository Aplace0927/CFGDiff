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
    try:
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
    except:
        discord.change_status(webhook_send.DiscordWebhookLogger.WebhookLogStatus.FAIL)

def ir_build(discord: webhook_send.DiscordWebhookLogger, chash: str) -> tuple[int, Optional[str]]:
    # logging.log(logging.WARN, f"Start building CHASH={chash}")
    try:
        cleanup(discord)
        discord.add_field(f":information_source: Generating LLVM BC of `{chash}`")
        return serial_jobs_configure(discord,
                [
                    (["git", "checkout", chash], CONFIG["OPENSSL_GIT_DIRECTORY"], True),

                    (["cp", "build_bitcode.sh", CONFIG["OPENSSL_GIT_DIRECTORY"]], CONFIG["CFGDIFF_IRCONV_DIRECTORY"], True),
                    (["cp", "comp_db_generate.py", CONFIG["OPENSSL_GIT_DIRECTORY"]], CONFIG["CFGDIFF_IRCONV_DIRECTORY"], True),

                    (["/bin/bash", "build_bitcode.sh"], CONFIG["OPENSSL_GIT_DIRECTORY"], True),

                    (["mv", f"./bcs", CONFIG["BUILD_OUTPUT_DIRECTORY"] + f"/openssl-bcs-{chash}"], CONFIG["OPENSSL_GIT_DIRECTORY"], True)
                ]
            )
    except:
        discord.change_status(webhook_send.DiscordWebhookLogger.WebhookLogStatus.FAIL)

def make_cfg(discord: webhook_send.DiscordWebhookLogger, chash: str) -> tuple[int, Optional[str]]:
    try:
        discord.add_field(f":bar_chart: Converting to CFG of `{chash}`")
        return serial_jobs_configure(discord,
                [
                    (["find", ".", "-type", "f", "-name", "*-lib-*", "-delete"], CONFIG["BUILD_OUTPUT_DIRECTORY"] + f"/openssl-bcs-{chash}", True), # Remove all libraries (except shared library output)
                    (["find", ".", "-exec", "opt", "-passes=dot-cfg", "-disable-output", "{}", ";"], CONFIG["BUILD_OUTPUT_DIRECTORY"] + f"/openssl-bcs-{chash}", True), # Convert to CFG
                    (["find", ".", "-type", "f", "-name", "*-shlib-*", "-delete"], CONFIG["BUILD_OUTPUT_DIRECTORY"] + f"/openssl-bcs-{chash}", True), # Remove all sh-libs.
                ]
            )
    except:
        discord.change_status(webhook_send.DiscordWebhookLogger.WebhookLogStatus.FAIL)

def cleanup(discord: webhook_send.DiscordWebhookLogger):
    try:
        discord.add_field(f":broom: Cleaning up building environment")
        return serial_jobs_configure(discord,
                [
                    (["git", "clean", "-fd"], CONFIG["OPENSSL_GIT_DIRECTORY"], True),
                    (["git", "reset", "--hard"], CONFIG["OPENSSL_GIT_DIRECTORY"], True),
                ]
            )
    except:
        discord.change_status(webhook_send.DiscordWebhookLogger.WebhookLogStatus.FAIL)

if __name__ == "__main__":

    with open(".setup", "r") as setup:
        CONFIG = {line.split()[0].strip(): line.split()[-1].strip() for line in setup.readlines()}
        
    for key in CONFIG:
        os.environ[key] = CONFIG[key] 

    commit_hash_pairs = read_commit_hashes()


    for vulnerable, patched in commit_hash_pairs:
        discord = webhook_send.DiscordWebhookLogger(WEBHOOK_URL, "Building Status", f"Diffing `{vulnerable}` `{patched}`")
        
        ir_build(discord, vulnerable)
        make_cfg(discord, vulnerable)

        ir_build(discord, patched)
        make_cfg(discord, patched)
        
        discord.change_status(webhook_send.DiscordWebhookLogger.WebhookLogStatus.SUCCESS)
        # webhook_send.success_webhook([f"Success Diff {vulnerable} {patched}"])