import math
import os
import re
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk


BYTES_PER_ROW = 16


def text_preview(data, encoding):
    codec = "cp037" if encoding == "EBCDIC" else "ascii"
    decoded = data.decode(codec, errors="replace")
    return "".join(
        character if character.isprintable() and character != "\ufffd" else "."
        for character in decoded
    )


def format_hex_rows(data, base_offset=0, bytes_per_row=BYTES_PER_ROW):
    rows = []
    for relative_offset in range(0, len(data), bytes_per_row):
        chunk = data[relative_offset:relative_offset + bytes_per_row]
        rows.append((
            f"{base_offset + relative_offset:08X}",
            " ".join(f"{byte:02X}" for byte in chunk),
            text_preview(chunk, "ASCII"),
            text_preview(chunk, "EBCDIC"),
        ))
    return rows


def extract_field_bytes(record, field):
    start = int(field["start"]) - 1
    length = int(field.get("length", int(field["end"]) - int(field["start"]) + 1))
    if start < 0 or length < 0:
        return b""
    return record[start:start + length]


def layout_type(field):
    declared_type = str(field.get("type", "")).upper()
    if declared_type in ("COMP", "COMP-3"):
        return declared_type
    if declared_type == "GROUP" or str(field.get("pic", "")).upper() == "GROUP":
        return "GROUP"
    return "DISPLAY"


def field_type(field, file_encoding="EBCDIC"):
    storage_type = layout_type(field)
    return file_encoding if storage_type == "DISPLAY" else storage_type


def decode_packed_decimal(field_bytes):
    if not field_bytes:
        return ""
    nibbles = [int(digit, 16) for digit in field_bytes.hex()]
    sign = nibbles.pop()
    if any(digit > 9 for digit in nibbles):
        return "Invalid COMP-3"
    if sign not in (0xA, 0xB, 0xC, 0xD, 0xE, 0xF):
        return "Invalid COMP-3"
    value = int("".join(str(digit) for digit in nibbles) or "0")
    if sign in (0xB, 0xD):
        value = -value
    return str(value)


def decode_binary_integer(field_bytes, field):
    if not field_bytes:
        return ""
    signed = str(field.get("pic", "")).upper().startswith("S")
    return str(int.from_bytes(field_bytes, byteorder="big", signed=signed))


def decode_field_value(field_bytes, field, file_encoding="EBCDIC"):
    data_type = layout_type(field)
    if data_type == "COMP-3":
        return decode_packed_decimal(field_bytes)
    if data_type == "COMP":
        return decode_binary_integer(field_bytes, field)
    if data_type == "GROUP":
        return ""
    return text_preview(field_bytes, file_encoding).rstrip()


def encode_field_value(value, field, file_encoding="EBCDIC"):
    data_type = layout_type(field)
    field_length = int(field.get("length", int(field["end"]) - int(field["start"]) + 1))

    if data_type == "DISPLAY":
        codec = "cp037" if file_encoding == "EBCDIC" else "ascii"
        try:
            encoded = value.encode(codec)
        except UnicodeEncodeError as error:
            raise ValueError(f"Value contains characters not supported by {file_encoding}.") from error
        if len(encoded) > field_length:
            raise ValueError(f"Value is {len(encoded)} bytes; field allows {field_length}.")
        pad = " ".encode(codec)
        return encoded + pad * (field_length - len(encoded))

    if data_type == "COMP":
        try:
            integer = int(value.strip(), 10)
        except ValueError as error:
            raise ValueError("COMP fields require a whole-number value.") from error
        signed = str(field.get("pic", "")).upper().startswith("S")
        try:
            return integer.to_bytes(field_length, byteorder="big", signed=signed)
        except OverflowError as error:
            raise ValueError(f"Value does not fit in this {field_length}-byte COMP field.") from error

    if data_type == "COMP-3":
        try:
            integer = int(value.strip(), 10)
        except ValueError as error:
            raise ValueError("COMP-3 fields require a whole-number value.") from error
        picture = str(field.get("pic", "")).upper()
        precision_match = re.search(r"9(?:\((\d+)\))?", picture)
        if not precision_match:
            raise ValueError(f"Cannot determine COMP-3 precision from PIC {picture!r}.")
        precision = int(precision_match.group(1) or "1")
        if integer < 0 and not picture.startswith("S"):
            raise ValueError("Negative values require a signed COMP-3 PIC.")
        if len(str(abs(integer))) > precision:
            raise ValueError(f"Value exceeds the {precision}-digit COMP-3 field.")
        digits = f"{abs(integer):0{precision}d}"
        nibbles = [int(digit) for digit in digits]
        nibbles = [0] * (field_length * 2 - 1 - len(nibbles)) + nibbles
        if len(nibbles) != field_length * 2 - 1:
            raise ValueError("Value does not fit in this COMP-3 field.")
        nibbles.append(0xD if integer < 0 else 0xC)
        return bytes((nibbles[index] << 4) | nibbles[index + 1] for index in range(0, len(nibbles), 2))

    raise ValueError(f"Fields with type {data_type} cannot be edited.")


def format_field_row(record, field, file_encoding="EBCDIC"):
    field_bytes = extract_field_bytes(record, field)
    data_type = field_type(field, file_encoding)
    decoded_value = decode_field_value(field_bytes, field, file_encoding)
    return (
        f"{int(field['start']) - 1:08X}",
        " ".join(f"{byte:02X}" for byte in field_bytes),
        data_type,
        decoded_value,
    )


class BinaryLabWindow(tk.Toplevel):
    def __init__(self, master, data_dir, layout_dir, app_directory, layout_loader):
        super().__init__(master)
        self.data_dir = data_dir
        self.layout_dir = layout_dir
        self.app_directory = app_directory
        self.layout_loader = layout_loader
        self.data = b""
        self.layout = []
        self.data_path = None
        self.layout_path = None
        self.current_record = 0
        self.record_length = 0
        self.record_count = 1
        self.file_encoding_var = tk.StringVar(self, value="EBCDIC")
        self.edit_value_var = tk.StringVar(self)
        self.is_dirty = False
        self.analysis_values = {}
        self._syncing_selection = False

        self.title("Binary Lab")
        self.geometry("1120x760")
        self.minsize(900, 600)
        self._build_menu()
        self._build_ui()
        self._refresh_record_controls()

    def _build_menu(self):
        menu_bar = tk.Menu(self)
        self.configure(menu=menu_bar)

        file_menu = tk.Menu(menu_bar, tearoff=False)
        file_menu.add_command(label="Open Binary File...", command=self.open_binary_file)
        file_menu.add_command(label="Load .FAD Layout...", command=self.load_layout)
        file_menu.add_separator()
        self.save_menu = file_menu
        file_menu.add_command(label="Save Binary File", command=self.save_binary_file, state="disabled")
        file_menu.add_separator()
        file_menu.add_command(label="Close", command=self.destroy)
        menu_bar.add_cascade(label="File", menu=file_menu)

        view_menu = tk.Menu(menu_bar, tearoff=False)
        view_menu.add_command(label="View Full Record...", command=self.view_full_record)
        menu_bar.add_cascade(label="View", menu=view_menu)

        layout_menu = tk.Menu(menu_bar, tearoff=False)
        layout_menu.add_command(label="Load .FAD Layout...", command=self.load_layout)
        layout_menu.add_command(label="Clear Layout", command=self.clear_layout)
        menu_bar.add_cascade(label="Layout", menu=layout_menu)

        tools_menu = tk.Menu(menu_bar, tearoff=False)
        tools_menu.add_command(label="Jump To Offset...", command=self.jump_to_offset)
        menu_bar.add_cascade(label="Tools", menu=tools_menu)

        help_menu = tk.Menu(menu_bar, tearoff=False)
        help_menu.add_command(
            label="About Binary Lab",
            command=lambda: messagebox.showinfo(
                "Binary Lab", "Raw-byte inspection with ASCII and EBCDIC previews.", parent=self
            ),
        )
        menu_bar.add_cascade(label="Help", menu=help_menu)

    def _build_ui(self):
        header = ttk.Frame(self, padding=(12, 10, 12, 6))
        header.pack(fill="x")
        ttk.Label(header, text="Binary Lab", font=("Segoe UI", 16, "bold")).pack(side="left")
        self.file_label = ttk.Label(header, text="No binary file loaded", anchor="e")
        self.file_label.pack(side="right", fill="x", expand=True, padx=(16, 4))

        controls = ttk.Frame(self, padding=(12, 4, 12, 10))
        controls.pack(fill="x")
        ttk.Button(controls, text="Open Binary File...", command=self.open_binary_file).pack(side="left")
        ttk.Button(controls, text="Load Layout...", command=self.load_layout).pack(side="left", padx=(6, 18))
        ttk.Label(controls, text="File Encoding:").pack(side="left", padx=(0, 5))
        encoding_dropdown = ttk.Combobox(
            controls,
            textvariable=self.file_encoding_var,
            values=("ASCII", "EBCDIC"),
            state="readonly",
            width=9,
        )
        encoding_dropdown.pack(side="left")
        encoding_dropdown.bind("<<ComboboxSelected>>", self._file_encoding_changed)

        navigation = ttk.Frame(controls)
        navigation.pack(side="right")
        self.previous_record_button = ttk.Button(
            navigation, text="Previous", command=self.previous_record, state="disabled"
        )
        self.previous_record_button.pack(side="left", padx=(0, 5))
        self.record_label = ttk.Label(navigation, text="Record 1 of 1", width=14, anchor="center")
        self.record_label.pack(side="left", padx=4)
        self.next_record_button = ttk.Button(
            navigation, text="Next", command=self.next_record, state="disabled"
        )
        self.next_record_button.pack(side="left", padx=(5, 0))

        panes = ttk.Panedwindow(self, orient="horizontal")
        panes.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        layout_frame = ttk.Frame(panes, padding=(0, 0, 8, 0))
        panes.add(layout_frame, weight=1)
        ttk.Label(layout_frame, text="Layout Fields").pack(anchor="w", pady=(0, 5))
        self.layout_tree = ttk.Treeview(
            layout_frame,
            columns=("name", "picture", "start", "length"),
            show="headings",
            selectmode="browse",
        )
        for column, title, width, anchor in (
            ("name", "Field Name", 160, "w"),
            ("picture", "Picture", 100, "w"),
            ("start", "Start", 55, "e"),
            ("length", "Length", 60, "e"),
        ):
            self.layout_tree.heading(column, text=title)
            self.layout_tree.column(column, width=width, anchor=anchor, stretch=column == "name")
        layout_scroll = ttk.Scrollbar(layout_frame, orient="vertical", command=self.layout_tree.yview)
        self.layout_tree.configure(yscrollcommand=layout_scroll.set)
        self.layout_tree.pack(side="left", fill="both", expand=True)
        layout_scroll.pack(side="right", fill="y")
        self.layout_tree.bind("<<TreeviewSelect>>", self._field_selected)

        hex_frame = ttk.Frame(panes)
        panes.add(hex_frame, weight=3)
        ttk.Label(hex_frame, text="Data Rows").pack(anchor="w", pady=(0, 5))
        columns = ("offset", "raw_hex", "type", "decoded")
        self.data_tree = ttk.Treeview(
            hex_frame, columns=columns, show="headings", selectmode="browse"
        )
        for column, title, width in (
            ("offset", "Offset", 90),
            ("raw_hex", "Raw Hex Bytes", 260),
            ("type", "Type", 100),
            ("decoded", "Decoded Value", 180),
        ):
            self.data_tree.heading(column, text=title)
            self.data_tree.column(
                column,
                width=width,
                anchor="w",
                stretch=column in ("raw_hex", "decoded"),
            )
        self.data_tree.tag_configure("even", background="#f2f5f7")
        self.data_tree.tag_configure("odd", background="#ffffff")
        data_scroll = ttk.Scrollbar(hex_frame, orient="vertical", command=self.data_tree.yview)
        data_horizontal_scroll = ttk.Scrollbar(
            hex_frame, orient="horizontal", command=self.data_tree.xview
        )
        self.data_tree.configure(
            yscrollcommand=data_scroll.set,
            xscrollcommand=data_horizontal_scroll.set,
        )
        data_horizontal_scroll.pack(side="bottom", fill="x")
        self.data_tree.pack(side="left", fill="both", expand=True)
        data_scroll.pack(side="right", fill="y")
        self.data_tree.bind("<<TreeviewSelect>>", self._field_selected)

        analysis = ttk.LabelFrame(self, text="Field Analysis", padding=(10, 8))
        analysis.pack(fill="x", padx=12, pady=(0, 10))
        analysis_fields = (
            ("Field Name", "name", 0, 2),
            ("Picture", "picture", 2, 1),
            ("Usage", "usage", 4, 1),
            ("Offset", "offset", 6, 1),
            ("Length", "length", 8, 1),
            ("Raw Bytes", "raw", 10, 3),
        )
        for label, key, column, span in analysis_fields:
            ttk.Label(analysis, text=label).grid(
                row=0, column=column, columnspan=span, sticky="w", padx=(0, 6), pady=(0, 3)
            )
            value_label = ttk.Label(analysis, text="", anchor="w")
            value_label.grid(
                row=1, column=column, columnspan=span, sticky="ew", padx=(0, 6), pady=(0, 8)
            )
            self.analysis_values[key] = value_label
            analysis.columnconfigure(column, weight=span)

        ttk.Label(analysis, text="Decoded Value").grid(
            row=2, column=0, sticky="nw", padx=(0, 8)
        )
        self.decoded_value_box = tk.Text(analysis, height=2, wrap="word", takefocus=False)
        self.decoded_value_box.grid(row=2, column=1, columnspan=12, sticky="ew")
        self.decoded_value_box.configure(state="disabled")

        ttk.Label(analysis, text="Edit Value").grid(
            row=3, column=0, sticky="nw", padx=(0, 8), pady=(8, 0)
        )
        self.edit_value_entry = ttk.Entry(analysis, textvariable=self.edit_value_var)
        self.edit_value_entry.grid(row=3, column=1, columnspan=10, sticky="ew", pady=(8, 0))
        self.apply_button = ttk.Button(analysis, text="Apply", command=self.apply_edit, state="disabled")
        self.apply_button.grid(row=3, column=11, sticky="e", padx=(8, 0), pady=(8, 0))

    def open_binary_file(self):
        path = filedialog.askopenfilename(
            parent=self,
            title="Open Binary File",
            initialdir=self.data_dir if os.path.isdir(self.data_dir) else self.app_directory,
            filetypes=[("All Files", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "rb") as binary_file:
                self.data = binary_file.read()
        except OSError as error:
            messagebox.showerror("Open Binary File", str(error), parent=self)
            return
        self.data_path = path
        self.is_dirty = False
        self.current_record = 0
        self.file_label.configure(text=f"File: {os.path.basename(path)}")
        self.save_menu.entryconfigure("Save Binary File", state="normal")
        self._update_record_count()
        self._render_field_rows()

    def load_layout(self):
        path = filedialog.askopenfilename(
            parent=self,
            title="Load FAD Layout",
            initialdir=self.layout_dir if os.path.isdir(self.layout_dir) else self.app_directory,
            filetypes=[("FAD Layouts", "*.fad")],
        )
        if not path:
            return
        try:
            fields = self.layout_loader(path)
        except (OSError, ValueError) as error:
            messagebox.showerror("Load FAD Layout", str(error), parent=self)
            return
        self.layout = fields
        self.layout_path = path
        self._update_record_count()
        self._render_field_rows()

    def clear_layout(self):
        self.layout = []
        self.layout_path = None
        self.record_length = 0
        self.current_record = 0
        self._update_record_count()
        self._render_field_rows()

    def _update_record_count(self):
        if self.layout:
            self.record_length = max(int(field["end"]) for field in self.layout)
            self.record_count = max(1, math.ceil(len(self.data) / self.record_length)) if self.record_length else 1
        else:
            self.record_length = 0
            self.record_count = 1
        self.current_record = min(self.current_record, self.record_count - 1)
        self._refresh_record_controls()

    def _refresh_record_controls(self):
        self.record_label.configure(text=f"Record {self.current_record + 1} of {self.record_count}")
        self.previous_record_button.configure(
            state="normal" if self.data and self.current_record > 0 else "disabled"
        )
        self.next_record_button.configure(
            state="normal" if self.data and self.current_record + 1 < self.record_count else "disabled"
        )

    def _current_record_bytes(self):
        if self.record_length:
            start = self.current_record * self.record_length
            return self.data[start:start + self.record_length]
        return self.data

    def _render_field_rows(self):
        selected = self.layout_tree.selection()
        selected_index = self.layout_tree.index(selected[0]) if selected else None
        self.layout_tree.delete(*self.layout_tree.get_children())
        self.data_tree.delete(*self.data_tree.get_children())
        record = self._current_record_bytes()

        for index, field in enumerate(self.layout):
            start = int(field["start"])
            end = int(field["end"])
            self.layout_tree.insert(
                "",
                "end",
                values=(field["name"], field["pic"], start, max(0, end - start + 1)),
            )
            self.data_tree.insert(
                "",
                "end",
                values=format_field_row(record, field, self.file_encoding_var.get()),
                tags=("even" if index % 2 == 0 else "odd",),
            )

        layout_rows = self.layout_tree.get_children()
        data_rows = self.data_tree.get_children()
        if not layout_rows:
            self._refresh_field_analysis()
            return
        if selected_index is None:
            selected_index = next(
                (index for index, field in enumerate(self.layout)
                 if str(field.get("pic", "")).upper() != "GROUP"),
                0,
            )
        selected_index = min(selected_index, len(layout_rows) - 1)
        self._syncing_selection = True
        try:
            self.layout_tree.selection_set(layout_rows[selected_index])
            self.data_tree.selection_set(data_rows[selected_index])
        finally:
            self._syncing_selection = False
        self._refresh_field_analysis()

    def _file_encoding_changed(self, event=None):
        self._render_field_rows()

    def _field_selected(self, event=None):
        if self._syncing_selection or event is None:
            return
        source = event.widget
        target = self.data_tree if source is self.layout_tree else self.layout_tree
        selection = source.selection()
        if not selection:
            return
        index = source.index(selection[0])
        target_rows = target.get_children()
        if index >= len(target_rows):
            return
        if target.selection() != (target_rows[index],):
            self._syncing_selection = True
            try:
                target.selection_set(target_rows[index])
                target.focus(target_rows[index])
                target.see(target_rows[index])
            finally:
                self._syncing_selection = False
        self._refresh_field_analysis()

    def _refresh_field_analysis(self):
        selected = self.layout_tree.selection()
        if not selected:
            for value_label in self.analysis_values.values():
                value_label.configure(text="")
            self.decoded_value_box.configure(state="normal")
            self.decoded_value_box.delete("1.0", tk.END)
            self.decoded_value_box.configure(state="disabled")
            self.edit_value_var.set("")
            self.edit_value_entry.configure(state="disabled")
            self.apply_button.configure(state="disabled")
            return
        index = self.layout_tree.index(selected[0])
        if index >= len(self.layout):
            return
        field = self.layout[index]
        field_bytes = extract_field_bytes(self._current_record_bytes(), field)
        decoded_value = decode_field_value(field_bytes, field, self.file_encoding_var.get())
        values = {
            "name": field["name"],
            "picture": field.get("pic", ""),
            "usage": layout_type(field),
            "offset": str(int(field["start"]) - 1),
            "length": str(field.get("length", int(field["end"]) - int(field["start"]) + 1)),
            "raw": " ".join(f"{byte:02X}" for byte in field_bytes),
        }
        for key, value in values.items():
            self.analysis_values[key].configure(text=value or "(empty)")
        self.decoded_value_box.configure(state="normal")
        self.decoded_value_box.delete("1.0", tk.END)
        self.decoded_value_box.insert(
            "1.0",
            decoded_value or "(empty)",
        )
        self.decoded_value_box.configure(state="disabled")
        self.edit_value_var.set(decoded_value)
        editable = layout_type(field) in ("DISPLAY", "COMP", "COMP-3") and self.data_path is not None
        self.edit_value_entry.configure(state="normal" if editable else "disabled")
        self.apply_button.configure(state="normal" if editable else "disabled")

    def apply_edit(self):
        selected = self.layout_tree.selection()
        if not selected or self.data_path is None:
            return
        index = self.layout_tree.index(selected[0])
        if index >= len(self.layout):
            return
        field = self.layout[index]
        try:
            encoded = encode_field_value(
                self.edit_value_var.get(), field, self.file_encoding_var.get()
            )
        except ValueError as error:
            messagebox.showerror("Apply Field Value", str(error), parent=self)
            return

        record_offset = self.current_record * self.record_length
        field_offset = record_offset + int(field["start"]) - 1
        if field_offset < 0 or field_offset + len(encoded) > len(self.data):
            messagebox.showerror(
                "Apply Field Value", "The selected field is outside the loaded binary data.", parent=self
            )
            return

        updated_data = bytearray(self.data)
        updated_data[field_offset:field_offset + len(encoded)] = encoded
        self.data = bytes(updated_data)
        self.is_dirty = True
        self.file_label.configure(text=f"File: {os.path.basename(self.data_path)} *")
        self._render_field_rows()

    def save_binary_file(self):
        if self.data_path is None:
            messagebox.showinfo("Save Binary File", "Open a binary file first.", parent=self)
            return
        try:
            with open(self.data_path, "wb") as binary_file:
                binary_file.write(self.data)
        except OSError as error:
            messagebox.showerror("Save Binary File", str(error), parent=self)
            return
        self.is_dirty = False
        self.file_label.configure(text=f"File: {os.path.basename(self.data_path)}")

    def view_full_record(self):
        record = self._current_record_bytes()
        window = tk.Toplevel(self)
        window.title(f"Full Record - Record {self.current_record + 1}")
        window.geometry("900x360")
        frame = ttk.Frame(window, padding=10)
        frame.pack(fill="both", expand=True)
        columns = ("offset", "hex", "ascii", "ebcdic")
        tree = ttk.Treeview(frame, columns=columns, show="headings")
        for column, title, width in (
            ("offset", "Offset", 90),
            ("hex", "Hex Bytes", 400),
            ("ascii", "ASCII", 180),
            ("ebcdic", "EBCDIC", 180),
        ):
            tree.heading(column, text=title)
            tree.column(column, width=width, anchor="w", stretch=column != "offset")
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        base_offset = self.current_record * self.record_length
        for values in format_hex_rows(record, base_offset=base_offset):
            tree.insert("", "end", values=values)

    def previous_record(self):
        if self.current_record > 0:
            self.current_record -= 1
            self._refresh_record_controls()
            self._render_field_rows()

    def next_record(self):
        if self.current_record + 1 < self.record_count:
            self.current_record += 1
            self._refresh_record_controls()
            self._render_field_rows()

    def jump_to_offset(self):
        offset = simpledialog.askinteger(
            "Jump To Offset", "Enter a zero-based offset within this record:", parent=self, minvalue=0
        )
        if offset is None:
            return
        for index, field in enumerate(self.layout):
            if int(field["start"]) - 1 <= offset < int(field["end"]):
                layout_row = self.layout_tree.get_children()[index]
                data_row = self.data_tree.get_children()[index]
                self.layout_tree.selection_set(layout_row)
                self.layout_tree.focus(layout_row)
                self.layout_tree.see(layout_row)
                self.data_tree.selection_set(data_row)
                self.data_tree.focus(data_row)
                self.data_tree.see(data_row)
                return