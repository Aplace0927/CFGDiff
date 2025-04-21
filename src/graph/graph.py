from .vertex import Vertex
from .edge import Edge


class Graph:
    def __init__(self):
        self.vertices: list[Vertex] = []
        self.edges: list[Edge] = []

    def find_vertex_by_addr(self, addr: int) -> Vertex:
        return [v for v in self.vertices if v.blk_addr == addr][0]

    def add_vertex(self, v: Vertex):
        self.vertices.append(v)

    def add_edge(self, e: Edge):
        self.edges.append(e)
        self.find_vertex_by_addr(e.src).successor[e.label] = e.dst
        self.find_vertex_by_addr(e.dst).predecessor.append(e.src)

    def assign_level(self):
        entry_point: Vertex = list(
            filter(lambda v: len(v.predecessor) == 0, self.vertices)
        )[0]
        entry_point.level = 0
        queue: list[Vertex] = [entry_point]
        while queue != []:
            v = queue.pop(0)

            for addr in v.successor.values():
                lv = self.find_vertex_by_addr(addr).level
                if lv is None:
                    self.find_vertex_by_addr(addr).level = v.level + 1
                    queue.append(
                        self.find_vertex_by_addr(addr)
                    )  # Only add unvisited nodes
                else:
                    self.find_vertex_by_addr(addr).level = min(
                        lv, v.level + 1
                    )  # How fast to reach this node
