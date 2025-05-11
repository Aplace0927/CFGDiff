import re
from typing import Optional


def instruction_parse(llvm_ir: list[str]):
    res = []
    for inst in llvm_ir:
        inst_split = inst.split()
        if "call" in inst:
            func_name = re.findall(
                "(@[\w]*)\(", inst
            )  # %ssa_id = call [type] @[func_name](args, *)
            if len(func_name) == 0:
                res.append("call ")
            else:
                res.append(f"call {func_name[0]}")
        elif inst_split[1] == "=":
            res.append(inst_split[2])
        else:
            res.append(inst_split[0])

    return res


class Vertex:
    def __init__(self, blk_addr: str = "", ssa_id: int = -1, llvm_ir: list[str] = []):
        self.blk_addr: str = blk_addr
        self.ssa_id: int = ssa_id
        self.llvm_ir: list[str] = llvm_ir
        self.llvm_ir_optype: list[str] = instruction_parse(self.llvm_ir)
        self.level: float = float("inf")

    def __hash__(self):
        return hash("\n".join(self.llvm_ir))

    def __eq__(self, other):
        return (
            isinstance(other, Vertex)
            and self.llvm_ir == other.llvm_ir
            and self.ssa_id == other.ssa_id
        )
