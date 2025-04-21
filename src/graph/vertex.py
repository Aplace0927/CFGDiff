import re
from typing import Optional


class Vertex:
    def __init__(self, blk_addr: str = "", ssa_id: int = -1, llvm_ir: list[str] = []):
        self.blk_addr: Optional[int] = (
            None if blk_addr == "" else int(blk_addr.strip("Node"), 0)
        )
        self.ssa_id: int = ssa_id
        self.llvm_ir: list[str] = llvm_ir
        self.llvm_ir_optype: list[str] = instruction_parse(self.llvm_ir)
        self.successor: dict[str, int] = {}
        self.predecessor: list[int] = []
        self.level: Optional[int] = None


def instruction_parse(llvm_ir: list[str]):
    res = []
    for inst in llvm_ir:
        inst_split = inst.split()
        if "call" in inst:
            func_name = re.findall(
                "(@[\w]*)\(", inst
            )  # %ssa_id = call [type] @[func_name](args, *)
            res.append(f"call {func_name}")
        elif inst_split[1] == "=":
            res.append(inst_split[2])
        else:
            res.append(inst_split[0])

    return res
