#!/usr/bin/env python3

import re
import sys
import r2pipe
import subprocess
import json
from pwn import *
from typing import *
from itertools import pairwise
from hashlib import sha256
from difflib import unified_diff

LLVM_OBJDUMP_PATH = os.environ.get("LLVM_PROJECT_PATH") + "/build/bin/llvm-objdump"
LLVM_NM_PATH = os.environ.get("LLVM_PROJECT_PATH") + "/build/bin/llvm-nm"
    

class BasicBlock:
    def __init__(
        self,
        symbol: str,
        start_addr: int,
        end_addr: int,
        jmp_true: Optional[int] = None,
        jmp_false: Optional[int] = None,
    ) -> None:
        self.symbol: str = symbol
        self.start_addr: int = start_addr
        self.end_addr: int = end_addr
        self.jmp_true: Optional[int] = jmp_true
        self.jmp_false: Optional[int] = jmp_false
        self.instructions: list[str] = []

    def __str__(self) -> str:
        if self.jmp_true and self.jmp_false:
            return f"<BasicBlock {hex(self.start_addr)} - {hex(self.end_addr)}> ?> {hex(self.jmp_true)} : {hex(self.jmp_false)}"
        elif self.jmp_true:
            return f"<BasicBlock {hex(self.start_addr)} - {hex(self.end_addr)}> -> {hex(self.jmp_true)}"
        else:
            return f"<BasicBlock {hex(self.start_addr)} - {hex(self.end_addr)}>"

    def add_instruction(self, inst: str):
        self.instructions.append(inst)

    def encode(self):
        return self.symbol + "." + sha256(
            "".join(
                [re.sub("<L[0-9]+>", "", ins) for ins in self.instructions]
            ).encode()
        ).hexdigest()


class Function:
    def __init__(self, base_addr: int, symbol: str) -> None:
        self.base_addr: int = base_addr
        self.end_addr: int = 0
        self.symbol: str = symbol
        self.blocks: list[BasicBlock] = []
        self.label_map: dict[str, int] = {}

    def add_block(self, block: BasicBlock):
        self.blocks.append(block)

    def find_block(self, addr: int) -> Optional[BasicBlock]:
        for block in self.blocks:
            if block.start_addr <= addr < block.end_addr:
                return block
        else:
            if self.base_addr <= addr < self.end_addr:
                for block in self.blocks:
                    if (
                        addr < block.start_addr
                    ):  # Should be guaranteed by the order of the blocks
                        block.start_addr = addr  # Append the start address of the block to its trampoline preceding `nop`s.
                        return block
            else:
                print(f"Addr {addr} is NOT in current function's address space {self.base_addr} ~ {self.end_addr}")


    def get_label_hash(self, label: str) -> str:
        return f"<{self.symbol}.{self.find_block(self.label_map[label]).encode()}>"
        

class Binary(ELF):
    def __init__(self, path, checksec=True, *args, **kwargs):
        super().__init__(path, checksec, *args, **kwargs)
        self.function_binary: list[Function] = []
        self.blocks_binary: list[BasicBlock] = []
        self.symbols_binary: dict[int, str] = {}

    def find_block(self, addr) -> Optional[BasicBlock]:
        for block in self.blocks_binary:
            if block.start_addr <= addr < block.end_addr:
                return block
        else:
            for block in self.blocks_binary:
                if (
                    addr < block.start_addr
                ):  # Should be guaranteed by the order of the blocks
                    block.start_addr = addr  # Append the start address of the block to its trampoline preceding `nop`s.
                    return block
        
    def invariant_blocks(self) -> list[str]:
        blocks_relation = []
        for block in self.blocks_binary:
            if block.jmp_true is not None and block.jmp_false is not None:
                blocks_relation.append(
                    f"{block.encode()} ?> {self.find_block(block.jmp_true).encode()} : {self.find_block(block.jmp_false).encode()}\n"
                )
            elif block.jmp_true is not None:
                blocks_relation.append(
                    f"{block.encode()} -> {self.find_block(block.jmp_true).encode()}\n"
                )
            else:
                blocks_relation.append(f"{block.encode()}\n")
        return blocks_relation

def extract_function_addr_symbols(path: str) -> list[tuple[int, str]]:
    nm = subprocess.check_output([LLVM_NM_PATH, path, "-v"])
    nm_list = []
    for line in nm.decode().splitlines():
        if found := re.findall(r"([0-9a-f]+) [tT] (.*)", line):
            nm_list.append((int(found[0][0], 16), found[0][1]))
    return nm_list


def setup_r2_environment(path: str) -> r2pipe.open:
    r2 = r2pipe.open(path)
    r2.cmd("aaaa")
    return r2


def extract_basic_block_addresses(r2p: r2pipe.open, fn_symbol: str, fn_addr: int) -> list[BasicBlock]:
    function_block = json.loads(
        r2p.cmd(f"afbj {fn_addr}")
    )  # [A]nalyze [F]unction [B]lock in [J]son

    block_list: list[BasicBlock] = []

    for blk_json in function_block:
        if "jump" in blk_json and "fail" in blk_json:
            block_list.append(
                BasicBlock(
                    fn_symbol,
                    blk_json["addr"],
                    blk_json["addr"] + blk_json["size"],
                    blk_json["jump"],
                    blk_json["fail"],
                )
            )
        elif "jump" in blk_json:
            block_list.append(
                BasicBlock(
                    fn_symbol,
                    blk_json["addr"],
                    blk_json["addr"] + blk_json["size"],
                    blk_json["jump"],
                )
            )
        else:
            block_list.append(
                BasicBlock(fn_symbol, blk_json["addr"], blk_json["addr"] + blk_json["size"])
            )

    return block_list


def extract_label_addresses(objdump_result: list[str]) -> dict[str, int]:
    label_addresses = {}
    for l1, l2 in pairwise(objdump_result):
        if found := re.findall(r"(<L[0-9]+>):", l1):
            label_addresses[found[0]] = int(l2.split(":")[0], 16)

    return label_addresses


def generate_llvm_objdump_of_function(
    path, fn: str, start_addr: int, stop_addr: int
) -> list[str]:
    try:
        objdump_result = subprocess.check_output(
            [
                LLVM_OBJDUMP_PATH,
                path,
                "--no-show-raw-insn",
                # "--no-addresses",
                "--x86-asm-syntax=intel",
                "--symbolize-operands",
                "-D",
                f"--disassemble-symbols={fn}",
                f"--start-address={start_addr}",
                f"--stop-address={stop_addr}",
            ],
        )
    except subprocess.CalledProcessError as e:
        print(f"Error: {e}")
        return ""

    objdump_result = [line.strip() for line in objdump_result.decode().splitlines()[6:]]
    return objdump_result


def substitute_glibc_offset_with_symbol(
    line: str, binary: ELF, sym_dict: dict[int, str]
) -> str:
    # <fn_name@GLIBC_version+offset>
    if (
        "GLIBC" not in line
        or (
            found := re.findall(
                r"<.*@GLIBC_[0-9]+\.[0-9]+\.[0-9]+\+(0x[0-9a-fA-F]+)>", line
            )
        )
        == []
    ):
        return line
    else:
        glibc_offset = int(found[0], 0)

        if glibc_offset in sym_dict:  # Offset is found in symbol lists
            return re.sub(
                r"<.*@GLIBC_[0-9]+\.[0-9]+\.[0-9]+\+(0x[0-9a-fA-F]+)>",
                f"<{sym_dict[glibc_offset]}>",
                line,
            )
        else:  # Offset is not found in symbol lists, fetch the string from the offset.

            try:
                string = f'"{re.sub(r'\W+', '', binary.string(glibc_offset).decode())}"'
            except:
                string = f"arrray{binary.string(glibc_offset).hex().capitalize()}"
            return re.sub(
                r"<.*@GLIBC_[0-9]+\.[0-9]+\.[0-9]+\+(0x[0-9a-fA-F]+)>",
                string,  #!TODO: Should be encoded
                line,
            )


def analyze(path: string) -> tuple[Binary, list[str]]:
    binary = Binary(path)
    functions_list = extract_function_addr_symbols(path)
    binary.symbols_binary = {v: k for k, v in binary.symbols.items()}  # addr -> symbol

    r2 = setup_r2_environment(path)

    for fn_base_addr, fn_symbol in functions_list:
        fn = Function(fn_base_addr, fn_symbol)

        blks = extract_basic_block_addresses(r2, fn_symbol, fn_base_addr)
        if len(blks) == 0:
            continue

        fn.blocks = blks
        fn.end_addr = max([blk.end_addr for blk in blks])

        fn_objdump = generate_llvm_objdump_of_function(
            path, fn.symbol, fn.base_addr, fn.end_addr
        )

        fn.label_map = extract_label_addresses(fn_objdump)
        for fn_objdump_line in fn_objdump:
            if (found := re.findall(r"^([0-9a-fA-F]+):", fn_objdump_line)) == []:
                continue
            addr = int(found[0], 16)
            target_blk = fn.find_block(addr)
            if target_blk is None:
                continue

            rewrited_line = " ".join(fn_objdump_line.split(":")[-1].strip().split())
            rewrited_line = substitute_glibc_offset_with_symbol(
                rewrited_line, binary, binary.symbols_binary
            )

            target_blk.add_instruction(rewrited_line)

        binary.function_binary.append(fn)
        binary.blocks_binary += blks

    for fn in binary.function_binary:
        for blk in fn.blocks:
                blk.instructions = [
                (
                    re.sub(r"<L[0-9]+>", fn.get_label_hash(found[0]), ins)
                    if (found := re.findall(r"<L[0-9]+>", ins)) != []
                    else ins
                )
                for ins in blk.instructions
            ]

    return binary, binary.invariant_blocks()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <binary1> <binary2>")
        sys.exit(1)

    bin_before, analyze_before = analyze(sys.argv[1])
    bin_after, analyze_after = analyze(sys.argv[2])

    diff = unified_diff(analyze_before, analyze_after, n=0)

    print(''.join(diff))
    