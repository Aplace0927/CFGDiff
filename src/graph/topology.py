import functools
import itertools
import pydot
import numpy as np
from scipy.optimize import linear_sum_assignment
import re
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.graph.graph import Graph
from src.graph.vertex import Vertex
from src.graph.edge import Edge


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


def vertex_edit_distance(v_old: Vertex, v_new: Vertex) -> int:
    inst_old = v_old.llvm_ir_optype
    inst_new = v_new.llvm_ir_optype
    dp_mat = np.zeros((len(inst_new) + 1, len(inst_old) + 1), dtype=np.uint32)

    for i, j in itertools.product(range(len(inst_new) + 1), range(len(inst_old) + 1)):
        if i == 0:
            dp_mat[i][j] = j
        elif j == 0:
            dp_mat[i][j] = i
        elif inst_new[i - 1] == inst_old[j - 1]:
            dp_mat[i][j] = dp_mat[i - 1][j - 1]
        else:
            dp_mat[i][j] = (
                min(dp_mat[i - 1][j - 1], dp_mat[i - 1][j], dp_mat[i][j - 1]) + 1
            )

    return dp_mat[-1][-1]


def match_vertice_forward(v: list[tuple[int, int]], src: int) -> int:
    _, dst = list(filter(lambda pair: pair[0] == src, v))[0]
    return dst


def match_vertice_backward(v: list[tuple[int, int]], dst: int) -> int:
    src, _ = list(filter(lambda pair: pair[1] == dst, v))[0]
    return src


def graph_isomorphism(
    g_old: Graph, g_new: Graph
) -> tuple[list[tuple[Vertex, Vertex]], tuple[list[Edge], list[Edge]]]:
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

    size_v_g_old = len(g_old.vertices)
    size_v_g_new = len(g_new.vertices)
    size_v_array = max(size_v_g_old, size_v_g_new)

    if size_v_g_new > size_v_g_old:
        for _ in range(size_v_g_new - size_v_g_old):
            g_old.add_vertex(Vertex())
    elif size_v_g_old > size_v_g_new:
        for _ in range(size_v_g_old - size_v_g_new):
            g_new.add_vertex(Vertex())

    assert len(g_old.vertices) == len(g_new.vertices)

    #   1.2. Setup the vertex-vertex edit distance graph
    #       Dim: [size_v_g_new * size_v_g_old]
    #       edit_dist[i][j] := d(Vo_i, Ve_j)

    edit_dist = np.empty((size_v_array, size_v_array), dtype=np.uint32)
    for (old_idx, old_node), (new_idx, new_node) in itertools.product(
        enumerate(g_old.vertices), enumerate(g_new.vertices)
    ):
        edit_dist[old_idx][new_idx] = vertex_edit_distance(old_node, new_node)

    # 2. Min-cost Bipartite Graph Matching

    v_old_id, v_new_id = map(list, linear_sum_assignment(edit_dist))
    match_cost = edit_dist[v_old_id, v_new_id]
    match_vertices_pair = [
        (g_old.vertices[old_id], g_new.vertices[new_id])
        for (old_id, new_id) in zip(v_old_id, v_new_id)
    ]
    match_vertices_addr = [
        (v_old.blk_addr, v_new.blk_addr) for (v_old, v_new) in match_vertices_pair
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

    g_old_edge_addr = [(v.src, v.dst) for v in g_old.edges]
    g_new_edge_addr = [(v.src, v.dst) for v in g_new.edges]

    deleted_edge = [
        e_old
        for e_old in g_old.edges
        if (
            (p_src := match_vertice_forward(match_vertices_addr, e_old.src)) == -1
            or (p_dst := match_vertice_forward(match_vertices_addr, e_old.dst)) == -1
            or (p_src, p_dst) not in g_new_edge_addr
        )
    ]

    added_edge = [
        e_new
        for e_new in g_new.edges
        if (
            (p_src := match_vertice_backward(match_vertices_addr, e_new.src)) == -1
            or (p_dst := match_vertice_backward(match_vertices_addr, e_new.dst)) == -1
            or (p_src, p_dst) not in g_old_edge_addr
        )
    ]

    return (diff_vertices, (deleted_edge, added_edge))


def build_cfg_from_dot(path: str) -> Graph:
    g = pydot.graph_from_dot_file(path)

    G = Graph()
    V = g[0].get_node_list()
    E = g[0].get_edge_list()

    for v in V:
        ssa_id, llvm_inst, jmp_target = node_label_preprocess(v.get_label())
        G.add_vertex(Vertex(v.get_name(), ssa_id, llvm_inst))

    for e in E:
        G.add_edge(Edge(e.get_source(), e.get_destination()))

    return G
