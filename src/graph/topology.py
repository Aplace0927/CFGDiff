import itertools
import os
import sys

import networkx as nx
import numpy as np
from scipy.optimize import linear_sum_assignment

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from src.graph.edge import Edge
from src.graph.vertex import Vertex


def node_label_preprocess(lab: str):
    label = (
        lab.replace("\\l...", "")
        .replace("\\l", "\n")
        .replace("{", "")
        .replace("}", "")
        .replace('"', "")
    )
    ssa_id, inst, *nextblk = label.split("|")
    inst_acc = []
    inside = False
    for i in inst.splitlines():
        if i.endswith("["):
            inside = True
            tmp = ""
        elif i.endswith("]") and "phi" not in i:
            inside = False
            inst_acc.append((tmp + i).strip())
            continue

        if inside:
            tmp += i + "\n"
        else:
            inst_acc.append(i.strip())
    return int(ssa_id.strip(":\n")), inst_acc, nextblk


def string_edit_distance(s_old: str, s_new: str) -> float:
    dp_mat = np.zeros((len(s_new) + 1, len(s_old) + 1), dtype=np.uint32)
    for i, j in itertools.product(range(len(s_new) + 1), range(len(s_old) + 1)):
        if i == 0:
            dp_mat[i][j] = j
        elif j == 0:
            dp_mat[i][j] = i
        elif s_new[i - 1] == s_old[j - 1]:
            dp_mat[i][j] = dp_mat[i - 1][j - 1]
        else:
            dp_mat[i][j] = (
                min(dp_mat[i - 1][j - 1], dp_mat[i - 1][j], dp_mat[i][j - 1]) + 1
            )
    return (
        1 - (dp_mat[-1][-1] / max_len)
        if (max_len := max(len(s_new), len(s_old)))
        else 1.0
    )


def vertex_edit_distance(v_old: Vertex, v_new: Vertex) -> float:
    inst_old = v_old.llvm_ir_optype
    inst_new = v_new.llvm_ir_optype
    dp_mat = np.zeros((len(inst_new) + 1, len(inst_old) + 1), dtype=np.float32)

    if len(inst_new) == 0 or len(inst_old) == 0:
        level_diff = 0xFFFFFFFF  # math.inf causes error in scipyl.linear_sum_assignment
    else:
        level_diff = abs(v_old.level - v_new.level)

    for i, j in itertools.product(range(len(inst_new) + 1), range(len(inst_old) + 1)):
        if i == 0:
            dp_mat[i][j] = j
        elif j == 0:
            dp_mat[i][j] = i
        elif inst_new[i - 1] == inst_old[j - 1]:
            dp_mat[i][j] = dp_mat[i - 1][j - 1]
        else:
            if inst_new[i - 1].startswith("call") and inst_old[j - 1].startswith(
                "call"
            ):
                dp_mat[i][j] = max(
                    dp_mat[i - 1][j - 1], dp_mat[i - 1][j], dp_mat[i][j - 1]
                ) + string_edit_distance(inst_new[i - 1], inst_old[j - 1])
            else:
                dp_mat[i][j] = (
                    max(dp_mat[i - 1][j - 1], dp_mat[i - 1][j], dp_mat[i][j - 1]) + 1
                )
    return dp_mat[-1][-1] + level_diff


def match_vertice_forward(v: list[tuple[int, int]], src: int) -> int:
    if len((found := list(filter(lambda pair: pair[0] == src, v)))) == 0:
        return None
    else:
        return found[0][1]


def match_vertice_backward(v: list[tuple[int, int]], dst: int) -> int:
    if len((found := list(filter(lambda pair: pair[1] == dst, v)))) == 0:
        return None
    else:
        return found[0][0]


def graph_isomorphism(g_old: nx.DiGraph, g_new: nx.DiGraph) -> tuple[
    list[tuple[Vertex, Vertex]],  # Same Vertices       - Mapping in (Old, New)
    list[tuple[Vertex, Vertex]],  # Different Vertices  - Mapping in (Old, New)
    list[tuple[str, str]],  # Vertex Address     - Mapping in (Old, New)
    list[tuple[Edge, Edge]],  # Conserved Edges     - Mapping in (Old, New)
    list[Edge],  # Deleted Edges
    list[Edge],  # Added Edges
]:
    #
    # G = <V, E>, where E := V -> V
    #
    # We have Go = <Vo, Eo>, Gn = <Vn, En>
    # To compare V:
    #   Vo -> Vn -> int.
    # To compare E:
    #   (Vo -> Vo) -> (Vn -> Vn) -> bool.

    # 1. Match Vertex-Vertex
    #   1.1. Put extra null node for excessive nodes, easier graph matching.

    size_v_g_old = g_old.number_of_nodes()
    size_v_g_new = g_new.number_of_nodes()
    size_v_array = max(size_v_g_old, size_v_g_new)

    if size_v_g_new > size_v_g_old:
        for idx in range(size_v_g_new - size_v_g_old):
            g_old.add_node(f"dummy_{idx}", vertex=Vertex())
    elif size_v_g_old > size_v_g_new:
        for idx in range(size_v_g_old - size_v_g_new):
            g_new.add_node(f"dummy_{idx}", vertex=Vertex())

    assert g_old.number_of_nodes() == g_new.number_of_nodes()

    #   1.2. Setup the vertex-vertex edit distance graph
    #       Dim: [size_v_g_new * size_v_g_old]
    #       edit_dist[i][j] := d(Vo_i, Ve_j)

    edit_dist = np.empty((size_v_array, size_v_array), dtype=np.float32)

    g_old_array_index = {
        old_idx: old_node for old_idx, old_node in enumerate(g_old.nodes)
    }
    g_new_array_index = {
        new_idx: new_node for new_idx, new_node in enumerate(g_new.nodes)
    }

    for (old_idx, old_node), (new_idx, new_node) in itertools.product(
        enumerate(g_old.nodes), enumerate(g_new.nodes)
    ):
        edit_dist[old_idx][new_idx] = vertex_edit_distance(
            g_old.nodes[old_node]["vertex"], g_new.nodes[new_node]["vertex"]
        )

    # 2. Min-cost Bipartite Graph Matching

    v_old_id, v_new_id = map(list, linear_sum_assignment(edit_dist))

    match_cost = edit_dist[v_old_id, v_new_id]
    match_vertices_pair = [
        (
            g_old.nodes[g_old_array_index[old_id]]["vertex"],
            g_new.nodes[g_new_array_index[new_id]]["vertex"],
        )
        for (old_id, new_id) in zip(v_old_id, v_new_id)
    ]

    match_vertices_addr = [
        (v_old.name, v_new.name) for (v_old, v_new) in match_vertices_pair
    ]

    same_vertices = [
        (vo, vn)
        for (vo, vn) in match_vertices_pair
        if vo.llvm_ir_optype == vn.llvm_ir_optype
    ]

    diff_vertices = [
        (vo, vn)
        for (vo, vn) in match_vertices_pair
        if vo.llvm_ir_optype != vn.llvm_ir_optype
    ]

    # 3. Apply Edges;
    #
    # v_o_src -(E_o)-> v_o_dst
    #    |               |
    # (Match)         (Match)
    #    |               |
    # v_n_src -(E_n)-> v_n_dst
    #
    # For each edge, both source and destination of edge
    # should be a matched basic blocks.

    conserved_edge = [
        (e_old, (e_new_src, e_new_dst))
        for e_old in g_old.edges
        if (
            (
                e_new_src := match_vertice_forward(match_vertices_addr, e_old[0]),
                e_new_dst := match_vertice_forward(match_vertices_addr, e_old[1]),
            )
            in g_new.edges
        )
    ]

    deleted_edge = [
        e_old
        for e_old in g_old.edges
        if (
            (p_src := match_vertice_forward(match_vertices_addr, e_old[0])) == -1
            or (p_dst := match_vertice_forward(match_vertices_addr, e_old[1])) == -1
            or (p_src, p_dst) not in g_new.edges
        )
    ]

    added_edge = [
        e_new
        for e_new in g_new.edges
        if (
            (p_src := match_vertice_backward(match_vertices_addr, e_new[0])) == -1
            or (p_dst := match_vertice_backward(match_vertices_addr, e_new[1])) == -1
            or (p_src, p_dst) not in g_old.edges
        )
    ]

    return (
        same_vertices,
        diff_vertices,
        match_vertices_addr,
        conserved_edge,
        deleted_edge,
        added_edge,
    )


def build_cfg_from_dot(path: str) -> nx.DiGraph:
    G: nx.DiGraph = nx.nx_pydot.read_dot(path)
    CFG: nx.DiGraph = nx.DiGraph()
    """
    Preprocess the graph notation.
    """

    for src, dst, branch in list(G.edges.data()):
        if len(data := src.split(":")) == 2:
            name, branch_from = data
            G.remove_edge(src, dst)
            G.add_edge(name, dst, branch=branch_from)

    for name, prop in list(G.nodes.data()):
        if len(data := name.split(":")) == 1:  # Node[addr]
            node_ssa_id, node_llvm_ir, node_br = node_label_preprocess(prop["label"])
            CFG.add_node(
                name, vertex=Vertex(name, ssa_id=node_ssa_id, llvm_ir=node_llvm_ir)
            )
        elif len(data) == 2:  # Node[addr]:branchname
            G.remove_node(name)
        else:
            raise Exception("Invalid node name format")

    for src, dst, branch in list(G.edges.data()):
        if len(data := src.split(":")) == 2:
            name, branch_from = data
            CFG.add_edge(name, dst, branch=f"{name}:{dst}:{branch_from}")
        else:
            CFG.add_edge(src, dst, branch=f"{src}:{dst}:next")

    for node, lvl in nx.single_source_shortest_path_length(
        CFG, [n for n in CFG.nodes if CFG.in_degree(n) == 0][0]
    ).items():
        CFG.nodes[node]["vertex"].level = lvl

    return CFG
