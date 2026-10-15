import re
import os
import tkinter as tk
from tkinter import filedialog

APP_DIRECTORY = os.path.dirname(os.path.abspath(__file__))
COPYBOOK_DIR = os.path.join(APP_DIRECTORY, "Copybook_files")
DATA_DIR = os.path.join(APP_DIRECTORY, "Data_files")
LAYOUT_DIR = os.path.join(APP_DIRECTORY, "Fad_files")


def default_fad_output(input_file):
    os.makedirs(LAYOUT_DIR, exist_ok=True)
    return os.path.join(LAYOUT_DIR, os.path.splitext(os.path.basename(input_file))[0] + ".fad")


# ------------------------------------------------------------
# PIC length calculator
# ------------------------------------------------------------
def pic_length(pic, usage=None):
    if not pic:
        return None
    pic = pic.strip().upper()
    if pic == "GROUP":
        return None
    m = re.match(r"X\((\d+)\)", pic)
    if m:
        return int(m.group(1))
    m = re.fullmatch(r"S?9\((\d+)\)", pic)
    if m:
        digits = int(m.group(1))
        if (usage or "").upper() == "COMP-3":
            return (digits + 2) // 2
        if (usage or "").upper() == "COMP":
            if digits <= 4:
                return 2
            if digits <= 9:
                return 4
            return 8
        return digits
    if pic in ("X", "9", "S9"):
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
    usage = None
    if " PIC " in stripped.upper():
        before_pic, after_pic = re.split(r"\bPIC\b", stripped, maxsplit=1, flags=re.IGNORECASE)
        before_pic = before_pic.strip()
        after_pic = after_pic.strip()

        tokens = before_pic.split(" ")
        name = tokens[1] if len(tokens) >= 2 else "FILLER"

        pic = after_pic.split(" ")[0]
        usage_match = re.search(r"\b(COMP-3|COMP-5|COMP)\b", after_pic, re.IGNORECASE)
        if usage_match:
            usage = usage_match.group(1).upper()
            if usage not in ("COMP", "COMP-3"):
                raise ValueError(f"Unsupported binary usage: {usage}; only COMP and COMP-3 are supported.")

    else:
        tokens = stripped.split(" ")
        name = tokens[1] if len(tokens) >= 2 else "FILLER"
        pic = "GROUP"

    return {
        "level": level,
        "name": name,
        "pic": pic,
        "usage": usage,
        "occurs": occurs,
        "children": [],
    }

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
        length = pic_length(node["pic"], node.get("usage"))
        if length is None:
            raise ValueError(f"Unsupported PIC clause: {node['pic']}")
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
def field_storage_type(node):
    if node["pic"] == "GROUP":
        return "GROUP"
    usage = node.get("usage")
    if usage:
        return usage
    return "DISPLAY"


def write_layout_row(out, level, name, node, fld, start, end, length):
    out.write(
        "%5d %-25s%-10s%5d%8d%8d%8d %-8s\n"
        % (level, name, node["pic"], fld, start, end, length, field_storage_type(node))
    )


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
            write_layout_row(
                out,
                node["level"],
                f"{node['name']}({n})",
                node,
                node["fld"],
                occ_start,
                occ_end,
                group_len,
            )

            # Children
            for child in node["children"]:
                child_len = child["length"]
                rel = child["start"] - base_start
                c_start = occ_start + rel
                c_end = c_start + child_len - 1

                write_layout_row(
                    out,
                    child["level"],
                    f"{child['name']}({n})",
                    child,
                    child["fld"],
                    c_start,
                    c_end,
                    child_len,
                )

        return

    # Normal field
    write_layout_row(
        out,
        node["level"],
        node["name"],
        node,
        node["fld"],
        node["start"],
        node["end"],
        node["length"],
    )

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

    return fad_output


class CopybookToLayout(tk.Frame):
    def __init__(self, master=None, **kwargs):
        super().__init__(master, **kwargs)
        self.copybook_path = tk.StringVar(value="")
        self.output_path = tk.StringVar(value="")

        self.configure(bg="#f0f0f0")
        self.grid_columnconfigure(1, weight=1)

        tk.Label(self, text="Copybook File:", bg="#f0f0f0", anchor="w").grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        self.copybook_entry = tk.Entry(self, textvariable=self.copybook_path, width=60)
        self.copybook_entry.grid(row=0, column=1, sticky="ew", padx=(0, 8), pady=(12, 6))
        tk.Button(self, text="Browse", command=self.browse_copybook).grid(row=0, column=2, padx=(0, 12), pady=(12, 6))

        tk.Label(self, text="Output .fad:", bg="#f0f0f0", anchor="w").grid(row=1, column=0, sticky="ew", padx=12, pady=6)
        self.output_entry = tk.Entry(self, textvariable=self.output_path, width=60)
        self.output_entry.grid(row=1, column=1, sticky="ew", padx=(0, 8), pady=6)

        tk.Button(self, text="Generate Layout", command=self.generate_layout).grid(row=2, column=1, sticky="w", padx=(0, 8), pady=(8, 12))

    def browse_copybook(self):
        path = filedialog.askopenfilename(
            title="Select COBOL Copybook",
            initialdir=COPYBOOK_DIR if os.path.isdir(COPYBOOK_DIR) else APP_DIRECTORY,
            filetypes=[("COBOL Copybook", "*.cbl"), ("Text Files", "*.txt"), ("All Files", "*.*")],
        )
        if not path:
            return

        self.copybook_path.set(path)
        self.output_path.set(default_fad_output(path))

    def generate_layout(self):
        input_file = self.copybook_path.get().strip()
        if not input_file:
            return

        output_file = self.output_path.get().strip() or default_fad_output(input_file)
        convert_copybook(input_file, output_file)


# ------------------------------------------------------------
# Run with File Dialog
# ------------------------------------------------------------
if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()

    input_file = filedialog.askopenfilename(
        title="Select COBOL Copybook",
        initialdir=COPYBOOK_DIR if os.path.isdir(COPYBOOK_DIR) else APP_DIRECTORY,
        filetypes=[("COBOL Copybook", "*.cbl"), ("Text Files", "*.txt"), ("All Files", "*.*")]
    )

    if not input_file:
        raise SystemExit

    fad_output = default_fad_output(input_file)
    convert_copybook(input_file, fad_output)
