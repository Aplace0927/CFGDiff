import json
import os
import subprocess
import sys
import networkx as nx
from networkx.algorithms import isomorphism

from colorama import Back, Fore, Style

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
import src.graph.topology as topology
import src.visual.diffview as diffview
from src.graph.vertex import Vertex

TARGET = "sm2_crypt"
FNAME = "ossl_sm2_plaintext_size"


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


def match_llvm_ir_optype(n1, n2):
    if n1["vertex"].llvm_ir_optype == n2["vertex"].llvm_ir_optype:
        return True
    else:
        return False


if __name__ == "__main__":
    setup_env()

    with open(f"compare/{TARGET}/compares_target.json", "r") as f:
        comp = json.load(f)

    graphs = [
        topology.build_cfg_from_dot(
            f"build_output/{TARGET}/openssl-bcs-{ver['hash']}/{FNAME}.dot"
        )
        for ver in comp
    ]

    patched, vulns, history = graphs[0], graphs[1], graphs[2:]

    diff_graph = nx.DiGraph()
    same_vert, diff_vert, _, con_edge, del_edge, new_edge = topology.graph_isomorphism(
        vulns, patched
    )

    del_vert, new_vert = zip(*diff_vert)

    # 1. Make as a set of CONNECTED COMPONENTS - as REMOVED and ADDED set
    # We define critical data and metadata as follows:
    # Critical data is the NODE/EDGE THAT IS EXACTLY DELTED OR ADDED.
    # Metadata is the NODE/EDGE THAT REQUIRED TO COMPLETE THE GRPAH DATASTRUCTURE from CRITICAL DATA.

    # Getting a connected component of the diff graph

    print("Del Vert:")
    for v in del_vert:
        if v.name == "":
            print("Dummy Vertex - Matching for Increased Graph Size")
        else:
            print(v.name)
            for suc in vulns.successors(v.name):
                if suc in [v.name for v in del_vert]:
                    print("\t->", suc, "STRONG MATCH")
                else:
                    print("\t->", suc)

            for pred in vulns.predecessors(v.name):
                if pred in [v.name for v in del_vert]:
                    print("\t<-", pred, "STRONG MATCH")
                else:
                    print("\t<-", pred)

    print("Del Edge:")
    for e in del_edge:
        print(vulns.edges[e])

    print("New Vert:")
    for v in new_vert:
        if v.name == "":
            print("Dummy Vertex - Matching for Increased Graph Size")
        else:
            print(v.name)
            for suc in patched.successors(v.name):
                if suc in [v.name for v in new_vert]:
                    print("\t->", suc, "STRONG MATCH")
                else:
                    print("\t->", suc)

            for pred in patched.predecessors(v.name):
                if pred in [v.name for v in new_vert]:
                    print("\t<-", pred, "STRONG MATCH")
                else:
                    print("\t<-", pred)

    print("New Edge:")
    for e in new_edge:
        print(patched.edges[e])

    # For ADDED set,
    #
    # [V0] -<E0>-> [V1]
    # [V0] -<E0>-> [V1] -<E1>-> [V2]
    #
    # Critical data is -<E1>-> [V2]. / Smallest Possible Metadata is [V1].

    # For REMOVED set,
    #
    # [VA] -<EA>-> [VB] -<EB>-> [VC]
    # [VA] -<EA>-> [VC]
    #
    # Critical data is [VB] -<EB>->. / Smallest Possible Metadata is [VA].

    # 2. Check original graph is exists.
    #
    # FORALL G := {Crt} + {Met} IN G' -> G has same vulnerability from the patch.

    # 3. Check the Mapped metadata graph is exists.
    #
    # FORALL G := {Crt} + Mapping({Met}) IN G' -> G WOULD have same vulnerability from the patch.
