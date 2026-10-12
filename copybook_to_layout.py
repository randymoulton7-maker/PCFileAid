import re
import os
import tkinter as tk
from tkinter import filedialog

# ------------------------------------------------------------
# PIC length calculator
# ------------------------------------------------------------
def pic_length(pic):
    if not pic:
        return None
    pic = pic.strip().upper()
    if pic == "GROUP":
        return None
    m = re.match(r"X\((\d+)\)", pic)
    if m:
        return int(m.group(1))
    m = re.match(r"9\((\d+)\)", pic)
    if m:
        return int(m.group(1))
    if pic in ("X", "9"):
        return 1
    return None

# ------------------------------------------------------------
# COPYBOOK line parser
# ------------------------------------------------------------
def parse_copybook_line(line):
    line = line.rstrip()

    # Skip blank lines
    if not line.strip():
        return None

    # Skip comment lines
    if line.lstrip().startswith("*"):
        return None

    # Normalize spacing
    stripped = line.strip()
    if stripped.endswith("."):
        stripped = stripped[:-1]
    stripped = re.sub(r"\s+", " ", stripped)

    # Abort if COMP / COMP-3 / COMP-5 appears
    upper_line = stripped.upper()
    if " COMP" in upper_line or "COMP-" in upper_line:
        print("ERROR: COMP / COMP-3 / COMP-5 fields detected.")
        print("Binary fields cannot be decoded safely on Windows.")
        print("Operation aborted.")
        raise SystemExit

    # Must start with a level number
    parts = stripped.split(" ")
    if not parts or not parts[0].isdigit():
        return None

    level = int(parts[0])
    occurs = None

    # Detect OCCURS
    occ = re.search(r"OCCURS\s+(\d+)\s+TIMES", stripped, re.IGNORECASE)
    if occ:
        occurs = int(occ.group(1))

    # Detect PIC clause
    if " PIC " in stripped.upper():
        before_pic, after_pic = re.split(r"\bPIC\b", stripped, maxsplit=1, flags=re.IGNORECASE)
        before_pic = before_pic.strip()
        after_pic = after_pic.strip()

        tokens = before_pic.split(" ")
        name = tokens[1] if len(tokens) >= 2 else "FILLER"

        pic = after_pic.split(" ")[0]

    else:
        tokens = stripped.split(" ")
        name = tokens[1] if len(tokens) >= 2 else "FILLER"
        pic = "GROUP"

    return {"level": level, "name": name, "pic": pic, "occurs": occurs, "children": []}

# ------------------------------------------------------------
# Build hierarchical tree
# ------------------------------------------------------------
def build_tree(lines):
    root = []
    stack = []
    for line in lines:
        node = parse_copybook_line(line)
        if not node:
            continue
        while stack and stack[-1]["level"] >= node["level"]:
            stack.pop()
        if stack:
            stack[-1]["children"].append(node)
        else:
            root.append(node)
        stack.append(node)
    return root

# ------------------------------------------------------------
# Assign FLD numbers and offsets
# ------------------------------------------------------------
def assign_offsets(node, offset, fld_counter):
    node["fld"] = fld_counter[0]
    fld_counter[0] += 1

    if node["pic"] != "GROUP":
        length = pic_length(node["pic"])
        node["length"] = length
        node["start"] = offset
        node["end"] = offset + length - 1
        return length

    group_len = 0
    child_offset = offset
    for child in node["children"]:
        child_len = assign_offsets(child, child_offset, fld_counter)
        child_offset += child_len
        group_len += child_len

    node["group_len"] = group_len

    if node["occurs"]:
        total_len = group_len * node["occurs"]
        node["length"] = total_len
        node["start"] = offset
        node["end"] = offset + total_len - 1
        return total_len

    node["length"] = group_len
    node["start"] = offset
    node["end"] = offset + group_len - 1
    return group_len

# ------------------------------------------------------------
# Write FileAid-style rows (flattened OCCURS, no blanks)
# ------------------------------------------------------------
def write_node(out, node):
    # GROUP with OCCURS: produce ONE line per occurrence, no blank lines
    if node["pic"] == "GROUP" and node.get("occurs"):
        occurs = node["occurs"]
        group_len = node["group_len"]
        base_start = node["start"]

        for n in range(1, occurs + 1):
            occ_start = base_start + (n - 1) * group_len
            occ_end = occ_start + group_len - 1

            # GROUP line
            out.write("%5d %-25s%-10s%5d%8d%8d%8d\n" %
                      (node["level"],
                       f"{node['name']}({n})",
                       "GROUP",
                       node["fld"],
                       occ_start, occ_end, group_len))

            # Children
            for child in node["children"]:
                child_len = child["length"]
                rel = child["start"] - base_start
                c_start = occ_start + rel
                c_end = c_start + child_len - 1

                out.write("%5d %-25s%-10s%5d%8d%8d%8d\n" %
                          (child["level"],
                           f"{child['name']}({n})",
                           child["pic"],
                           child["fld"],
                           c_start, c_end, child_len))

        return

    # Normal field
    out.write("%5d %-25s%-10s%5d%8d%8d%8d\n" %
              (node["level"], node["name"], node["pic"],
               node["fld"], node["start"], node["end"], node["length"]))

    for child in node["children"]:
        write_node(out, child)

# ------------------------------------------------------------
# Main conversion
# ------------------------------------------------------------
def convert_copybook(input_file, fad_output):
    with open(input_file, "r") as f:
        lines = f.readlines()

    tree = build_tree(lines)

    fld_counter = [1]
    offset = 1
    for node in tree:
        used = assign_offsets(node, offset, fld_counter)
        offset += used

    with open(fad_output, "w") as out:
        out.write("-------- FIELD LEVEL/NAME --------- --PICTURE--    FLD  START     END  LENGTH\n\n")
        for node in tree:
            write_node(out, node)

    print("Layout file written to:", fad_output)

# ------------------------------------------------------------
# Run with File Dialog
# ------------------------------------------------------------
if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()

    input_file = filedialog.askopenfilename(
        title="Select COBOL Copybook",
        filetypes=[("COBOL Copybook", "*.cbl"), ("Text Files", "*.txt"), ("All Files", "*.*")]
    )

    if not input_file:
        print("No file selected.")
        raise SystemExit

    fad_output = os.path.splitext(input_file)[0] + ".fad"
    convert_copybook(input_file, fad_output)
