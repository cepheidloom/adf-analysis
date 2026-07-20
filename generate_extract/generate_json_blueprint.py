#!/usr/bin/env python3
"""
json_blueprint.py — Generates a compact structural blueprint of a JSON file.

No actual values are ever written — only field names, types, and structure.

Usage:
    python json_blueprint.py <file.json> [--mode tree|flat] [output.txt]
    
    python json_blueprint.py data.json --mode flat   # AI input → smallest
    python json_blueprint.py data.json --mode tree   # human reading → visual
    python json_blueprint.py data.json               # defaults to tree

Modes:
    tree  (default) — indented box-drawing tree, easy to read visually
    flat            — one dot-path per line, minimal tokens, best for AI input

If no output path is given, saves as <file>_blueprint_tree.txt or _flat.txt
"""

import json
import sys
import os
from datetime import datetime


# ── Type helpers ──────────────────────────────────────────────────────────────

def get_type(value):
    if value is None:            return "null"
    if isinstance(value, bool):  return "boolean"  # must come before int
    if isinstance(value, int):   return "integer"
    if isinstance(value, float): return "float"
    if isinstance(value, str):   return "string"
    if isinstance(value, list):  return "array"
    if isinstance(value, dict):  return "object"
    return type(value).__name__


def array_inner_type(lst):
    """'array of objects [5 items]', 'array of strings [3 items]', etc."""
    if not lst:
        return "array(empty)"
    types = {get_type(i) for i in lst}
    inner = types.pop() if len(types) == 1 else f"mixed({','.join(sorted(types))})"
    plural = inner if inner.endswith("s") else inner + "s"
    return f"array of {plural} [{len(lst)} item{'s' if len(lst) != 1 else ''}]"


def unique_array_samples(lst):
    """Return one representative item per unique structure in an array."""
    seen, samples = [], []
    for item in lst:
        if isinstance(item, dict):
            sig = tuple(sorted(item.keys()))
            if sig not in seen:
                seen.append(sig)
                samples.append(item)
        elif isinstance(item, list):
            samples.append(item)
            break
    return samples


# ── Stats ─────────────────────────────────────────────────────────────────────

def count_fields(value):
    if isinstance(value, dict):
        return 1 + sum(count_fields(v) for v in value.values())
    if isinstance(value, list):
        if not value: return 1
        seen, total = [], 1
        for item in value:
            if isinstance(item, dict):
                sig = tuple(sorted(item.keys()))
                if sig not in seen:
                    seen.append(sig)
                    total += count_fields(item)
            elif isinstance(item, list):
                total += count_fields(item)
                break
        return total
    return 1


def max_depth(value, depth=0):
    if isinstance(value, dict):
        if not value: return depth
        return max(max_depth(v, depth + 1) for v in value.values())
    if isinstance(value, list):
        if not value: return depth
        return max(max_depth(i, depth + 1) for i in value)
    return depth


# ── MODE 1: Tree renderer ─────────────────────────────────────────────────────

PIPE  = "│   "
TEE   = "├── "
LAST  = "└── "
BLANK = "    "


def render_tree(value, lines, prefix="", label="root", is_last=True):
    connector    = LAST if is_last else TEE
    child_prefix = prefix + (BLANK if is_last else PIPE)

    if isinstance(value, dict):
        lines.append(f"{prefix}{connector}{label}  (object)")
        keys = list(value.keys())
        for i, key in enumerate(keys):
            render_tree(value[key], lines, child_prefix, key, i == len(keys) - 1)

    elif isinstance(value, list):
        lines.append(f"{prefix}{connector}{label}  ({array_inner_type(value)})")
        samples = unique_array_samples(value)
        for i, sample in enumerate(samples):
            render_tree(sample, lines, child_prefix, "[item]", i == len(samples) - 1)

    else:
        lines.append(f"{prefix}{connector}{label}  -> {get_type(value)}")


def build_tree(data, fname, fields, depth):
    header = [
        "=" * 56,
        "  JSON BLUEPRINT  (tree mode)",
        f"  File     : {fname}",
        f"  Fields   : {fields}   Max depth: {depth}",
        f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "  Note     : No values — structure only.",
        "=" * 56,
        "",
    ]
    lines = []
    render_tree(data, lines)
    legend = [
        "",
        "-" * 56,
        "LEGEND",
        "  (object)           key/value container",
        "  (array of X [N])   list — structure sampled once",
        "  -> type            leaf field type",
        "-" * 56,
    ]
    return "\n".join(header + lines + legend) + "\n"


# ── MODE 2: Flat path renderer ────────────────────────────────────────────────

def render_flat(value, lines, path="root"):
    if isinstance(value, dict):
        lines.append(f"{path} (object)")
        for key, val in value.items():
            render_flat(val, lines, f"{path}.{key}")

    elif isinstance(value, list):
        lines.append(f"{path} ({array_inner_type(value)})")
        for sample in unique_array_samples(value):
            render_flat(sample, lines, f"{path}[]")

    else:
        lines.append(f"{path} -> {get_type(value)}")


def build_flat(data, fname, fields, depth):
    header = [
        f"# JSON BLUEPRINT (flat mode) | file:{fname} | fields:{fields} | depth:{depth} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | no values",
        "",
    ]
    lines = []
    render_flat(data, lines)
    return "\n".join(header + lines) + "\n"


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]

    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)

    # Parse --mode flag
    mode = "tree"
    if "--mode" in args:
        idx = args.index("--mode")
        if idx + 1 >= len(args):
            print("Error: --mode requires a value: tree or flat")
            sys.exit(1)
        mode = args[idx + 1]
        if mode not in ("tree", "flat"):
            print("Error: --mode must be 'tree' or 'flat'")
            sys.exit(1)
        args = args[:idx] + args[idx + 2:]

    if not args:
        print("Error: no input file given.")
        sys.exit(1)

    input_path = args[0]
    if len(args) >= 2:
        output_path = args[1]
    else:
        base = os.path.splitext(input_path)[0]
        output_path = base + f"_blueprint_{mode}.txt"

    # Load JSON
    try:
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # data = data["linked_services"]
    except FileNotFoundError:
        print(f"Error: file not found — {input_path}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: invalid JSON — {e}")
        sys.exit(1)

    fname  = os.path.basename(input_path)
    fields = count_fields(data)
    depth  = max_depth(data)

    if mode == "flat":
        content = build_flat(data, fname, fields, depth)
    else:
        content = build_tree(data, fname, fields, depth)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"✅  Blueprint saved : {output_path}")
    print(f"    Mode            : {mode}")
    print(f"    Fields mapped   : {fields}")
    print(f"    Max depth       : {depth}")
    print(f"    Output size     : {os.path.getsize(output_path)} bytes")


if __name__ == "__main__":
    main()