import os
import subprocess
import json
import sys


def setup_env() -> dict[str, str]:
    with open(".setup", "r") as setup:
        config = {
            line.split()[0].strip(): line.split()[-1].strip()
            for line in setup.readlines()
        }

        for key in config:
            os.environ[key] = config[key]
    return config


def git_checkout_to_hash(bid: str):
    basedir = os.environ.get("OPENSSL_GIT_DIRECTORY")
    subprocess.run(["git", "checkout", bid], cwd=basedir)


def check_file_commit_hash(fname: str):
    basedir = os.environ.get("OPENSSL_GIT_DIRECTORY")
    file = basedir + "/" + fname
    proc = subprocess.run(
        ["git", "log", '--format="%H"', file], cwd=basedir, capture_output=True
    )

    return proc.stdout.decode().replace('"', "").splitlines()


def fetch_symbols_from_file(fname: str) -> list[str]:
    basedir = os.environ.get("OPENSSL_GIT_DIRECTORY")
    file = basedir + "/" + fname

    proc = subprocess.run(
        ["ctags", "--languages=C", "--kinds-C=f", "--output-format=json", file],
        cwd=basedir,
        capture_output=True,
    )

    return [
        json.loads(func_info).get("name")
        for func_info in proc.stdout.decode().splitlines()
    ]


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"[+] Usage: {sys.argv[0]} file")
        exit(-1)

    setup_env()
    cfg_check_list = []
    commit_hash_list = check_file_commit_hash(sys.argv[1])
    for commit_hash in commit_hash_list:
        git_checkout_to_hash(commit_hash)
        cfg_check_list.append(
            {"hash": commit_hash, "symbol": fetch_symbols_from_file(sys.argv[1])}
        )

    with open("compares_target.json", "w") as out:
        json.dump(cfg_check_list, out, indent=4)
