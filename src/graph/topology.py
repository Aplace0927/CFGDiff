import itertools
import os
import sys

import networkx as nx
import numpy as np
from scipy.optimize import linear_sum_assignment

from typing import Iterable

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from src.graph.edge import Edge
from src.graph.vertex import Vertex

IR_DIFF_WEIGHT = 0.50
LEVEL_DIFF_WEIGHT = 0.20
INDEG_DIFF_WEIGHT = 0.15
OUTDEG_DIFF_WEIGHT = 0.15

assert (
    round(
        IR_DIFF_WEIGHT + LEVEL_DIFF_WEIGHT + INDEG_DIFF_WEIGHT + OUTDEG_DIFF_WEIGHT, 3
    )
    == 1.000
)


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


def boolean_edit_distance(s_old: Iterable, s_new: Iterable) -> float:
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
    return dp_mat[-1][-1] / max(len(s_new), len(s_old), 1)


def vertex_edit_distance(
    g_old: nx.DiGraph, g_new: nx.digraph, v_old: str, v_new: str
) -> float:
    v_old_vertex, v_new_vertex = (
        g_old.nodes[v_old]["vertex"],
        g_new.nodes[v_new]["vertex"],
    )

    """
    - Edit distance of LLVM IR abst instr
    - Level difference
    - Indegree / Outdegree difference
    """

    inst_old = v_old_vertex.llvm_ir_optype
    inst_new = v_new_vertex.llvm_ir_optype

    """
    LEVEL DIFFERENCE.
    Position-wise percent similarity of the instruction. (between 0 and 1)
    """
    if v_old_vertex.level == -1 or v_new_vertex.level == -1:
        level_diff = 1  # Match with nonexistent node costs 1
    else:
        v_old_percent = v_old_vertex.level / max(
            max(g_old.nodes[v]["vertex"].level for v in g_old.nodes), 1
        )
        v_new_percent = v_new_vertex.level / max(
            max(g_new.nodes[v]["vertex"].level for v in g_new.nodes), 1
        )
        level_diff = abs(v_old_percent - v_new_percent)

    """
    In/Out degree difference.
    - The range of possible values of degree is [0, inf]. 
    - MOST OF THE BLOCK HAS:
        - 1 IN / 1 OUT for normal block
        - 0 IN / n OUT for entry block
        - n IN / 0 OUT for exit block
        - 2 OUT for branch block
        - n OUT for switch block

    However most of blocks have less than 2 in/out degree.
    Otherwise, that block could be determined as a fixed point of graph matching.
    """

    # IMPLEMENTATION
    indeg_diff = abs(g_new.in_degree(v_new) - g_old.in_degree(v_old)) / max(
        max(g_new.in_degree(v_new), g_old.in_degree(v_old)), 1
    )
    outdeg_diff = abs(g_new.out_degree(v_new) - g_old.out_degree(v_old)) / max(
        max(g_new.out_degree(v_new), g_old.out_degree(v_old)), 1
    )

    """
    IR Edit distance.
    Since we are diffing between versions, most of each block's instruction length could be conserved.
    """

    if v_old_vertex.level == -1 or v_new_vertex.level == -1:
        ir_diff = 1
    else:
        ir_diff = boolean_edit_distance(inst_old, inst_new)

    inst_old_call_ops = [op for op in inst_old if op.startswith("call")]
    inst_new_call_ops = [op for op in inst_new if op.startswith("call")]

    if inst_old_call_ops and inst_new_call_ops:
        ir_diff *= 0.3
        ir_diff += 0.7 * boolean_edit_distance(inst_old_call_ops, inst_new_call_ops)

    return (
        ir_diff * IR_DIFF_WEIGHT
        + level_diff * LEVEL_DIFF_WEIGHT
        + indeg_diff * INDEG_DIFF_WEIGHT
        + outdeg_diff * OUTDEG_DIFF_WEIGHT
    )


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
            g_old, g_new, old_node, new_node
        )

    # 2. Min-cost Bipartite Graph Matching

    v_old_vertex_id, v_new_vertex_id = map(list, linear_sum_assignment(edit_dist))

    match_cost = edit_dist[v_old_vertex_id, v_new_vertex_id]
    match_vertices_pair = [
        (
            g_old.nodes[g_old_array_index[old_id]]["vertex"],
            g_new.nodes[g_new_array_index[new_id]]["vertex"],
        )
        for (old_id, new_id) in zip(v_old_vertex_id, v_new_vertex_id)
    ]

    match_vertices_addr = [
        (v_old_vertex.name, v_new_vertex.name)
        for (v_old_vertex, v_new_vertex) in match_vertices_pair
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


def get_root_node(g: nx.DiGraph) -> str:
    return [n for n in g.nodes if g.in_degree(n) == 0][0]


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
        CFG, get_root_node(CFG)
    ).items():
        CFG.nodes[node]["vertex"].level = lvl

    return CFG
