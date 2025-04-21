import os
import sys
import subprocess
import pydot
from typing import Optional

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from ..graph import graph, vertex, edge, topology

RED_COLOR = "#e78284"
GREEN_COLOR = "#a6d189"
BLACK_COLOR = "#303446"
GREY_COLOR = "#acb0be"
WHITE_COLOR = "#c6d0f5"


def generate_diffview(
    vertex_same: list[tuple[vertex.Vertex, vertex.Vertex]],
    vertex_diff: list[tuple[vertex.Vertex, vertex.Vertex]],
    vertex_addr_matching: list[tuple[Optional[int], Optional[int]]],
    edge_same: list[tuple[edge.Edge, edge.Edge]],
    edge_del: list[edge.Edge],
    edge_add: list[edge.Edge],
    **kwargs,
) -> None:
    """
    Generate a diff view of the two graphs.
    """

    # Create a new graph for the diff view
    func_name = kwargs.get("func_name") or ""
    commit_hash = kwargs.get("commit_hash") or ""

    diff_graph = pydot.Graph(
        func_name + "_" + commit_hash,
        graph_type="digraph",
        compound="true",  # Enable subgraph clustering
        rankdir="TB",  # Top to bottom layout
    )

    # Add vertices and edges from both graphs to the diff graph
    same_pairs = []
    for v_same_old, v_same_new in vertex_same:
        same_pairs.append((v_same_old.blk_addr, v_same_new.blk_addr))
        diff_graph.add_node(
            pydot.Node(
                f"{hex(v_same_old.blk_addr)}_{hex(v_same_new.blk_addr)}",
                label="{"
                + f"{str(v_same_old.level)}_{str(v_same_new.level)}\l"
                + f"{hex(v_same_old.blk_addr)}_{hex(v_same_new.blk_addr)}\l|\t"
                + "\l\t".join(v_same_old.llvm_ir_optype)
                + "}",
                shape="record",
                fontname="Courier",
                style="filled",
                fillcolor=GREY_COLOR,
            )
        )

    clustered_pairs = []
    for v_diff_old, v_diff_new in vertex_diff:
        null_node = pydot.Node(
            "NULL",
            label="NULL",
            shape="record",
            fontname="Courier",
            style="filled",
            fillcolor=BLACK_COLOR,
        )

        if v_diff_old.llvm_ir_optype == []:
            if v_diff_new.llvm_ir_optype == []:  # Empty -> Empty
                raise Exception("Both vertices are empty")
            else:  # Empty -> Something
                old_node = null_node
                new_node = pydot.Node(
                    f"NULL_{hex(v_diff_new.blk_addr)}",
                    label="{"
                    + f"NULL_{str(v_diff_new.level)}\l"
                    + f"NULL_{hex(v_diff_new.blk_addr)}\l|\t"
                    + "\l\t".join(v_diff_new.llvm_ir_optype)
                    + "}",
                    shape="record",
                    fontname="Courier",
                    style="filled",
                    fillcolor=GREEN_COLOR,
                )
                # diff_graph.add_node(old_node)
                diff_graph.add_node(new_node)
        else:
            if v_diff_new.llvm_ir_optype == []:  # Something -> Empty
                old_node = pydot.Node(
                    f"{hex(v_diff_old.blk_addr)}_NULL",
                    label="{"
                    + f"{str(v_diff_old.level)}_NULL\l"
                    + f"{hex(v_diff_old.blk_addr)}_NULL\l|\t"
                    + "\l\t".join(v_diff_old.llvm_ir_optype)
                    + "}",
                    shape="record",
                    fontname="Courier",
                    style="filled",
                    fillcolor=RED_COLOR,
                )
                new_node = null_node
                diff_graph.add_node(old_node)
                # diff_graph.add_node(new_node)

            else:  # Something -> Something
                clustered_pairs.append(
                    f"{hex(v_diff_old.blk_addr)}_{hex(v_diff_new.blk_addr)}"
                )
                old_node = pydot.Node(
                    f"{hex(v_diff_old.blk_addr)}_{hex(v_diff_new.blk_addr)}_old",
                    label="{"
                    + f"{str(v_diff_old.level)}_{str(v_diff_new.level)}_old\l"
                    + f"{hex(v_diff_old.blk_addr)}_{hex(v_diff_new.blk_addr)}\l|\t"
                    + "\l\t".join(v_diff_old.llvm_ir_optype)
                    + "}",
                    shape="record",
                    fontname="Courier",
                    style="filled",
                    fillcolor=RED_COLOR,
                )
                new_node = pydot.Node(
                    f"{hex(v_diff_old.blk_addr)}_{hex(v_diff_new.blk_addr)}_new",
                    label="{"
                    + f"{str(v_diff_old.level)}_{str(v_diff_new.level)}_new\l"
                    + f"{hex(v_diff_old.blk_addr)}_{hex(v_diff_new.blk_addr)}\l|\t"
                    + "\l\t".join(v_diff_new.llvm_ir_optype)
                    + "}",
                    shape="record",
                    fontname="Courier",
                    style="filled",
                    fillcolor=GREEN_COLOR,
                )
                cluster = pydot.Subgraph(
                    f"cluster_{hex(v_diff_old.blk_addr)}_{hex(v_diff_new.blk_addr)}",
                    label=f"{str(v_diff_old.level)}_{str(v_diff_new.level)}_diff\l"
                    + f"{hex(v_diff_old.blk_addr)}_{hex(v_diff_new.blk_addr)}",
                    shape="record",
                    fontname="Courier",
                    color=GREY_COLOR,
                )
                cluster.add_node(old_node)
                cluster.add_node(new_node)
                diff_graph.add_subgraph(cluster)

    to_text = lambda s: "NULL" if s is None else hex(s)

    for edge_same_old, edge_same_new in edge_same:
        if (edge_same_old.src, edge_same_new.src) in same_pairs:
            if (edge_same_old.dst, edge_same_new.dst) in same_pairs:
                # Source same, Dest same (Node -> Node)
                edge_source = (
                    f"{to_text(edge_same_old.src)}_{to_text(edge_same_new.src)}"
                )
                edge_destination = (
                    f"{to_text(edge_same_old.dst)}_{to_text(edge_same_new.dst)}"
                )
                options = {}
            else:
                # Source same, Dest diff (Node -> Cluster)
                edge_source = (
                    f"{to_text(edge_same_old.src)}_{to_text(edge_same_new.src)}"
                )
                edge_destination = (
                    f"{to_text(edge_same_old.dst)}_{to_text(edge_same_new.dst)}_old"
                )
                options = {
                    "lhead": f"cluster_{to_text(edge_same_old.dst)}_{to_text(edge_same_new.dst)}"
                }
        else:
            if (edge_same_old.dst, edge_same_new.dst) in same_pairs:
                # Source diff, Dest same (Cluster -> Node)
                edge_source = (
                    f"{to_text(edge_same_old.src)}_{to_text(edge_same_new.src)}_old"
                )
                edge_destination = (
                    f"{to_text(edge_same_old.dst)}_{to_text(edge_same_new.dst)}"
                )
                options = {
                    "ltail": f"cluster_{to_text(edge_same_old.src)}_{to_text(edge_same_new.src)}"
                }
            else:
                # Source diff, Dest diff (Cluster -> Cluster)
                edge_source = (
                    f"{to_text(edge_same_old.src)}_{to_text(edge_same_new.src)}_old"
                )
                edge_destination = (
                    f"{to_text(edge_same_old.dst)}_{to_text(edge_same_new.dst)}_old"
                )
                options = {
                    "ltail": f"cluster_{to_text(edge_same_old.src)}_{to_text(edge_same_new.src)}",
                    "lhead": f"cluster_{to_text(edge_same_old.dst)}_{to_text(edge_same_new.dst)}",
                }

        diff_graph.add_edge(
            pydot.Edge(
                edge_source,
                edge_destination,
                color=GREY_COLOR,
                **options,
            )
        )

    for e_del in edge_del:
        e_old_src, e_old_dst = to_text(e_del.src), to_text(e_del.dst)
        e_new_src, e_new_dst = (
            to_text(topology.match_vertice_forward(vertex_addr_matching, e_del.src)),
            to_text(topology.match_vertice_forward(vertex_addr_matching, e_del.dst)),
        )

        if f"{e_old_src}_{e_new_src}" in clustered_pairs:
            if f"{e_old_dst}_{e_new_dst}" in clustered_pairs:
                edge_source = f"{e_old_src}_{e_new_src}_old"
                edge_destination = f"{e_old_dst}_{e_new_dst}_old"
                options = {
                    "ltail": f"cluster_{e_old_src}_{e_new_src}",
                    "lhead": f"cluster_{e_old_dst}_{e_new_dst}",
                }
            else:
                edge_source = f"{e_old_src}_{e_new_src}_old"
                edge_destination = f"{e_old_dst}_{e_new_dst}"
                options = {
                    "ltail": f"cluster_{e_old_src}_{e_new_src}",
                }
        else:
            if f"{e_old_dst}_{e_new_dst}" in clustered_pairs:
                edge_source = f"{e_old_src}_{e_new_src}"
                edge_destination = f"{e_old_dst}_{e_new_dst}_old"
                options = {
                    "lhead": f"cluster_{e_old_dst}_{e_new_dst}",
                }
            else:
                edge_source = f"{e_old_src}_{e_new_src}"
                edge_destination = f"{e_old_dst}_{e_new_dst}"
                options = {}

        diff_graph.add_edge(
            pydot.Edge(
                edge_source,
                edge_destination,
                color=RED_COLOR,
                style="dotted",
                penwidth=2.0,
                **options,
            )
        )

    for e_add in edge_add:
        e_new_src, e_new_dst = to_text(e_add.src), to_text(e_add.dst)
        e_old_src, e_old_dst = (
            to_text(topology.match_vertice_backward(vertex_addr_matching, e_add.src)),
            to_text(topology.match_vertice_backward(vertex_addr_matching, e_add.dst)),
        )

        if f"{e_old_src}_{e_new_src}" in clustered_pairs:
            if f"{e_old_dst}_{e_new_dst}" in clustered_pairs:
                edge_source = f"{e_old_src}_{e_new_src}_old"
                edge_destination = f"{e_old_dst}_{e_new_dst}_old"
                options = {
                    "ltail": f"cluster_{e_old_src}_{e_new_src}",
                    "lhead": f"cluster_{e_old_dst}_{e_new_dst}",
                }
            else:
                edge_source = f"{e_old_src}_{e_new_src}_old"
                edge_destination = f"{e_old_dst}_{e_new_dst}"
                options = {
                    "ltail": f"cluster_{e_old_src}_{e_new_src}",
                }
        else:
            if f"{e_old_dst}_{e_new_dst}" in clustered_pairs:
                edge_source = f"{e_old_src}_{e_new_src}"
                edge_destination = f"{e_old_dst}_{e_new_dst}_old"
                options = {
                    "lhead": f"cluster_{e_old_dst}_{e_new_dst}",
                }
            else:
                edge_source = f"{e_old_src}_{e_new_src}"
                edge_destination = f"{e_old_dst}_{e_new_dst}"
                options = {}

        diff_graph.add_edge(
            pydot.Edge(
                edge_source,
                edge_destination,
                color=GREEN_COLOR,
                style="dashed",
                penwidth=2.0,
                **options,
            )
        )

    # Save the diff graph to a file
    with open(f"diffview_{func_name}_{commit_hash}.dot", "w") as f:
        f.write(diff_graph.to_string(indent="\t"))

    subprocess.run(
        [
            "dot",
            "-Tpng",
            f"diffview_{func_name}_{commit_hash}.dot",
            "-o",
            f"diffview_{func_name}_{commit_hash}.png",
        ]
    )
