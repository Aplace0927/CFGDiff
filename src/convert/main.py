import os
import subprocess
import json
import itertools
import sys
from itertools import pairwise
from colorama import Fore, Back, Style
import networkx as nx

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
import src.graph.topology as topology
import src.visual.diffview as diffview

TARGET = "statemem_client"


def file_diff(f_new: str, f_old: str) -> bool:
    h_new = subprocess.run(["sha256sum", f_new], capture_output=True).stdout.split()[0]
    h_old = subprocess.run(["sha256sum", f_old], capture_output=True).stdout.split()[0]
    return h_new.split()[0] == h_old.split()[0]


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
    setup_env()

    with open(f"compare/{TARGET}/compares_target.json", "r") as f:
        comp = json.load(f)

    for v_new, v_old in pairwise(comp):

        # --Suggestion.
        # Get a "Patch" with v[0] and v[1], and
        # Compare the (v[0], {v[2], v[3] ... v[n]}) to detect the diff-ed vulnerability

        # v_new = comp[0]
        # for v_old in comp[1:]:

        new_hash, new_fn = v_new["hash"], set(v_new["symbol"])
        old_hash, old_fn = v_old["hash"], set(v_old["symbol"])

        new_built_set = set(
            [
                fname[:-4]
                for fname in os.listdir(
                    f"build_output/{TARGET}/openssl-bcs-{new_hash}/"
                )
            ]
        )
        old_built_set = set(
            [
                fname[:-4]
                for fname in os.listdir(
                    f"build_output/{TARGET}/openssl-bcs-{old_hash}/"
                )
            ]
        )

        new_fn &= new_built_set
        old_fn &= old_built_set

        fn_only_new = new_fn - old_fn
        fn_only_old = old_fn - new_fn
        fn_intersect = new_fn & old_fn

        hash_same, hash_diff = [], []

        for f in fn_intersect:
            Gn = topology.build_cfg_from_dot(
                f"build_output/{TARGET}/openssl-bcs-{new_hash}/{f}.dot"
            )
            Go = topology.build_cfg_from_dot(
                f"build_output/{TARGET}/openssl-bcs-{old_hash}/{f}.dot"
            )

            (v_same, v_diff, v_addr_matching, e_con, e_old, e_new) = (
                topology.graph_isomorphism(Go, Gn)
            )

            if v_diff == [] and e_old == [] and e_new == []:
                continue

            print(
                f"{Style.BRIGHT}{Back.RED}{f} @ {old_hash}{Style.RESET_ALL} vs\n{Style.BRIGHT}{Back.GREEN}{f} @ {new_hash}{Style.RESET_ALL}"
            )

            if v_diff != []:
                for v_old, v_new in v_diff:
                    if v_old.llvm_ir != []:
                        print(
                            Fore.RED
                            + "- [\n\t"
                            + ";\n- \t".join(v_old.llvm_ir)
                            + "\n- ]"
                        )
                    if v_new.llvm_ir != []:
                        print(
                            Fore.GREEN
                            + "+ [\n\t"
                            + ";\n+ \t".join(v_new.llvm_ir)
                            + "\n+ ]\n"
                        )

            for edge in e_old:
                v_src, v_dst = Go.nodes[edge[0]]["vertex"], Go.nodes[edge[1]]["vertex"]

                print(
                    Fore.RED
                    + f"- {Go.edges[edge]['branch']}:\n- {v_src.llvm_ir_optype} ->\n- {v_dst.llvm_ir_optype}\n"
                )

            for edge in e_new:
                v_src, v_dst = Gn.nodes[edge[0]]["vertex"], Gn.nodes[edge[1]]["vertex"]

                print(
                    Fore.GREEN
                    + f"+ {Gn.edges[edge]['branch']}:\n+ {v_src.llvm_ir_optype} ->\n+ {v_dst.llvm_ir_optype}\n"
                )

            """diffview.generate_diffview(
                v_same,
                v_diff,
                v_addr_matching,``
                e_con,
                e_old,
                e_new,
                func_name=f,
                commit_hash=new_hash + "_" + old_hash,
            )"""

# Edit distance calculation should include the function symbol.
