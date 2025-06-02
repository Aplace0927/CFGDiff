import json
import os
import subprocess
import sys
from typing import Callable

import networkx as nx
from colorama import Back, Fore, Style
from networkx.algorithms import isomorphism

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
import src.graph.topology as topology
import src.visual.diffview as diffview
from src.graph.vertex import Vertex

# TARGET = "bn_sqrt"
# FNAME = "BN_mod_sqrt"

TARGET = "libarchive"
FNAME = "header_gnu_longlink"


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


def construct_graph(target: str, hash: str, fname: str):
    return topology.build_cfg_from_dot(
        # f"build_output/{target}/openssl-bcs-{hash}/{fname}.dot"
        f"build_output/{target}/libarchive-bcs-{hash}/{fname}.dot"
    )


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


def match_forward_vertex(
    diff: list[tuple[Vertex, Vertex]],
) -> tuple[Callable[[str], str | None], Callable[[str], str | None]]:
    fw_dict = {old.name: new for (old, new) in diff if old.name != ""}

    def get_block_from_prev(blk: str) -> Vertex | None:
        return next(filter(lambda x: x[0].name == blk, diff))[0]

    def get_block_from_after(blk: str) -> Vertex | None:
        return next(filter(lambda x: x[1].name == blk, diff))[1]

    def match_forward(blk_prev: str) -> str | None:
        if match := fw_dict.get(blk_prev):
            return match.name
        else:
            return None

    def conserve_forward(blk_prev: str) -> bool:
        if match := fw_dict.get(blk_prev):
            return all(
                item in iter(get_block_from_after(match).llvm_ir_optype)
                for item in get_block_from_prev(blk_prev).llvm_ir_optype
            )
        else:
            return False

    return match_forward, conserve_forward


def match_backward_vertex(
    diff: list[tuple[Vertex, Vertex]],
) -> tuple[Callable[[str], str | None], Callable[[str], str | None]]:
    bw_dict = {new.name: old.name for (old, new) in diff if new.name != ""}

    def get_block_from_prev(blk: str) -> Vertex | None:
        return next(filter(lambda x: x[0].name == blk, diff))[0]

    def get_block_from_after(blk: str) -> Vertex | None:
        return next(filter(lambda x: x[1].name == blk, diff))[1]

    def match_backward(blk_after: str) -> str | None:
        if match := bw_dict.get(blk_after):
            return match
        else:
            return None

    def conserve_backward(blk_after: str) -> bool:
        if match := bw_dict.get(blk_after):
            return all(
                item in iter(get_block_from_after(blk_after).llvm_ir_optype)
                for item in get_block_from_prev(match).llvm_ir_optype
            )
        else:
            return False

    return match_backward, conserve_backward


def find_vertex_previous(name: str, diff: list[tuple[Vertex, Vertex]]) -> bool:
    return any(map(lambda x: x[0].name == name, diff))


def find_vertex_after(name: str, diff: list[tuple[Vertex, Vertex]]) -> bool:
    return any(map(lambda x: x[1].name == name, diff))


def find_vertex_in(name: str, single: list[Vertex]) -> bool:
    return any(map(lambda x: x.name == name, single))


if __name__ == "__main__":
    setup_env()

    with open(f"compare/{TARGET}/compares_target.json", "r") as f:
        comp = json.load(f)

    graphs = [ver["hash"] for ver in comp]

    patched, vulns, history = graphs[0], graphs[1], graphs[2:]

    diff_graph = nx.DiGraph()

    patched_graph = construct_graph(TARGET, patched, FNAME)

    same_vert, diff_vert, _, con_edge, del_edge, new_edge = topology.graph_isomorphism(
        construct_graph(TARGET, vulns, FNAME), patched_graph
    )

    del_vert, new_vert = zip(*diff_vert)

    del_vert = list(filter(lambda x: x.name != "", del_vert))
    new_vert = list(filter(lambda x: x.name != "", new_vert))

    # 1. Make as a set of CONNECTED COMPONENTS - as REMOVED and ADDED set
    # We define critical data and metadata as follows:
    # Critical data is the NODE/EDGE THAT IS EXACTLY DELTED OR ADDED.
    # Metadata is the NODE/EDGE THAT REQUIRED TO COMPLETE THE GRPAH DATASTRUCTURE from CRITICAL DATA.

    # Getting a connected component of the diff graph

    # 2. Check original graph is exists.

    # <-- Vn --- V0 ---- P -->
    #    {n} ... {n} -> {  }     Deleted Node | Should be conserved in the previous graph |  If not detected -> Actually Vuln, but judged Benign. (False Negative)
    #    { } ... { } -> {n'}       Added Node | Should not exist, but detecting may cause FP.
    #   {e'} ... {e} -> {  }     Deleted Edge | Should be conserved in the previous graph |  If not detected -> Actually Vuln, but judged Benign. (False Negative)
    #   {  } ... {e} -> {e }       Added Edge | Should not exist.                         |  If     detected -> Actually Benign, but judged Vuln. (False Positive)

    for h in history:
        # Deleted components
        print(
            f"{Style.BRIGHT + Back.GREEN}+ {patched}{Style.RESET_ALL} vs "
            f"{Style.BRIGHT + Back.RED}- {vulns}{Style.RESET_ALL} -> "
            f"{Style.BRIGHT + Back.YELLOW}? {h}{Style.RESET_ALL}"
        )
        history_graph = construct_graph(TARGET, h, FNAME)
        same_v, diff_v, _, con_e, del_e, new_e = topology.graph_isomorphism(
            history_graph, construct_graph(TARGET, vulns, FNAME)
        )

        match_bw, conserve_bw = match_backward_vertex(diff_v + same_v)

        (tp, tn, fp, fn) = 0, 0, 0, 0

        # Deleted Vertex
        # Node should be CONSERVED in the original graph
        #     DETECTED: Actually Vuln, Judged Vuln   -> TP
        # NOT DETECTED: Actually Vuln, Judged Benign -> FN
        for v in del_vert:
            if conserve_bw(v.name) and match_bw(v.name):
                print(
                    f"{Fore.GREEN + Style.BRIGHT}[DEL VERT]{Style.RESET_ALL} ✅ [{v.name}] => [{match_bw(v.name)}]"
                )
                tp += 1
            elif not conserve_bw(v.name) and match_bw(v.name):
                print(
                    f"{Fore.RED + Style.BRIGHT}[DEL VERT]{Style.RESET_ALL} ❌ [{v.name}] =>  {match_bw(v.name)} "
                    f"( {v.llvm_ir_optype} => {history_graph.nodes[match_bw(v.name)]['vertex'].llvm_ir_optype} )"
                )
                fn += 1

            else:
                print(
                    f"{Fore.RED + Style.BRIGHT}[DEL VERT]{Style.RESET_ALL} ❌ [{v.name}] => ?"
                )
                fn += 1

        # Delted Edge
        # Edge should be exist between the nodes; which should be CONSERVED if node is in the conserved one, else MATCHED.
        #     DETECTED: Actually Vuln, Judged Vuln   -> TP
        # NOT DETECTED: Actually Vuln, Judged Benign -> FN

        for src, dst in del_edge:
            if find_vertex_in(src, del_vert) and find_vertex_in(src, del_vert):
                src_bw, dst_bw = match_bw(src), match_bw(dst)
                if (
                    conserve_bw(src)
                    and conserve_bw(dst)
                    and history_graph.has_edge(src_bw, dst_bw)
                ):
                    print(
                        f"{Fore.GREEN + Style.BRIGHT}[DEL EDGE]{Style.RESET_ALL} ✅ ([{src}] -> [{dst}]) => ([{src_bw}] -> [{dst_bw}])"
                    )
                    tp += 1
                else:
                    print(
                        f"{Fore.RED + Style.BRIGHT}[DEL EDGE]{Style.RESET_ALL} ❌ ([{src}] -> [{dst}]) => ( {src_bw}  ??  {dst_bw} )"
                    )
                    fn += 1

            elif find_vertex_previous(src, same_vert) and find_vertex_in(dst, del_vert):
                src_bw, dst_bw = match_bw(src), match_bw(dst)
                if conserve_bw(dst) and history_graph.has_edge(src_bw, dst_bw):
                    print(
                        f"{Fore.GREEN + Style.BRIGHT}[DEL EDGE]{Style.RESET_ALL} ✅ ( {src}  -> [{dst}]) => ( {src_bw}  -> [{dst_bw}])"
                    )
                    tp += 1
                else:
                    print(
                        f"{Fore.RED + Style.BRIGHT}[DEL EDGE]{Style.RESET_ALL} ❌ ( {src}  -> [{dst}]) => ( {src_bw}  ??  {dst_bw} )"
                    )
                    fn += 1

            elif find_vertex_in(src, del_vert) and find_vertex_previous(dst, same_vert):
                src_bw, dst_bw = match_bw(src), match_bw(dst)
                if conserve_bw(src) and history_graph.has_edge(src_bw, dst_bw):
                    print(
                        f"{Fore.GREEN + Style.BRIGHT}[DEL EDGE]{Style.RESET_ALL} ✅ ([{src}] ->  {dst} ) => ([{src_bw}] ->  {dst_bw} )"
                    )
                    tp += 1
                else:
                    print(
                        f"{Fore.RED + Style.BRIGHT}[DEL EDGE]{Style.RESET_ALL} ❌ ([{src}] ->  {dst} ) => ( {src_bw}  ??  {dst_bw} )"
                    )
                    fn += 1

            elif find_vertex_previous(src, same_vert) and find_vertex_previous(
                dst, same_vert
            ):
                src_bw, dst_bw = match_bw(src), match_bw(dst)
                if history_graph.has_edge(src_bw, dst_bw):
                    print(
                        f"{Fore.GREEN + Style.BRIGHT}[DEL EDGE]{Style.RESET_ALL} ✅ ( {src}  ->  {dst} ) => ( {src_bw}  ->  {dst_bw} )"
                    )
                    tp += 1
                else:
                    print(
                        f"{Fore.RED + Style.BRIGHT}[DEL EDGE]{Style.RESET_ALL} ❌ ( {src}  ->  {dst} ) => ( {src_bw}  ??  {dst_bw} )"
                    )
                    fn += 1
            else:
                Exception("Neither source nor destination is in the del_edge list")

        # Added components
        history_graph = construct_graph(TARGET, h, FNAME)
        same_v, diff_v, _, con_e, del_e, new_e = topology.graph_isomorphism(
            history_graph, construct_graph(TARGET, patched, FNAME)
        )

        match_fw, conserve_fw = match_forward_vertex(diff_v + same_v)

        # NEW VERTEX.
        # Pass. If there is a new simple vertex (`br` and `store`),
        # it should be generate a easy false-positive.
        #     DETECTED: Actually Benign, Judged Vuln   -> FP
        # NOT DETECTED: Actually Benign, Judged Benign -> TN

        # NEW EDGE.
        for src, dst in new_edge:
            if match_fw(src) and match_fw(dst):
                if conserve_fw(src) and conserve_fw(dst):
                    src_fw, dst_fw = match_fw(src), match_fw(dst)
                    if history_graph.has_edge(src_fw, dst_fw):
                        print(
                            f"{Fore.RED + Style.BRIGHT}[NEW EDGE]{Style.RESET_ALL} ❌ ([{src}] -> [{dst}]) => ([{src_fw}] -> [{dst_fw}])"
                        )
                        fp += 1
                    else:
                        print(
                            f"{Fore.GREEN + Style.BRIGHT}[NEW EDGE]{Style.RESET_ALL} ✅ ([{src}] -> [{dst}]) => ([{src_fw}] -- [{dst_fw}])"
                        )
                        tn += 1
                else:
                    print(
                        f"{Fore.GREEN + Style.BRIGHT}[NEW EDGE]{Style.RESET_ALL} ✅ ([{src}] -> [{dst}]) => ( {src_fw}  --  {dst_fw} )"
                    )
                    tn += 1
            else:
                print(
                    f"{Fore.GREEN + Style.BRIGHT}[NEW EDGE]{Style.RESET_ALL} ✅ ({src} -> {dst}) => ?"
                )
                tn += 1

        print(
            f"=== {Style.BRIGHT + Fore.YELLOW}{h}{Style.RESET_ALL} ===\n"
            f"{Style.BRIGHT + Back.GREEN}TP {tp:3d}{Style.RESET_ALL} {Style.BRIGHT + Back.RED}FP {fp:3d}{Style.RESET_ALL} | ACCURC {(tp + tn) / (tp + fp + tn + fn):.4f}\n"
            f"{Style.BRIGHT + Fore.RED}FN {fn:3d}{Style.RESET_ALL} {Style.BRIGHT + Fore.GREEN}TN {tn:3d}{Style.RESET_ALL} | RECALL {tp / (tp + fn):.4f}  PRECIS {tp / (tp + fp):.4f}\n"
        )
