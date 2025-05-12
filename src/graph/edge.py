"""
class Edge:
    def __init__(self, src_addr: str, dst_addr: str):
        if len(source := src_addr.strip("Node").split(":")) == 2:
            self.src: int = int(source[0], 0)
            self.label: str = source[1]
        else:
            self.src = int(source[0], 0)
            self.label: str = "next"

        self.dst: str = int(dst_addr.strip("Node"), 0)
"""

Edge = tuple[str, str]
