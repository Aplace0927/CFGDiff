#!/usr/bin/env python3

import sys
import re

def find_node_ssa_id(dat: list[str]) -> dict[str, str]:
    rename_dict = {}
    for line in dat:
        if (found := re.findall(r'label="{([0-9]+):\\l', line)) != []:
            rename_dict[line.split()[0].strip("[]")] = "Node" + found[0]
    return rename_dict

def unhide(s: str) -> str:
    return '/'.join(s.split('/')[:-1]) + '/' + s.split('/')[-1].strip('.')

def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <.cfg.dot>")

    cfg_data = open(sys.argv[1]).read()
    cfg_data_lines = cfg_data.splitlines()

    rename_dict = find_node_ssa_id(cfg_data_lines)

    with open(unhide(sys.argv[1]), "w") as normalized_cfg:
        for key in rename_dict:
            cfg_data = cfg_data.replace(key, rename_dict[key])
        normalized_cfg.write(cfg_data)

main()