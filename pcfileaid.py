import tkinter as tk
from tkinter import ttk, filedialog, simpledialog, messagebox
from tkinter import colorchooser
from copybook_to_layout import CopybookToLayout, COPYBOOK_DIR, DATA_DIR, LAYOUT_DIR
from binary_lab import BinaryLabWindow

# ------------------------------------------------------------
# NEW: Theme model + config store (cleaner, maintainable design)
# ------------------------------------------------------------
import json
import os
import glob
from dataclasses import dataclass, field

CONFIG_FILENAME = "pcfileaid_config.json"
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), CONFIG_FILENAME)
APP_DIRECTORY = os.path.dirname(os.path.abspath(__file__))
KEY_DEFINITION_CONFIG_FILE = os.path.join(
    APP_DIRECTORY, "record_type_config.json"
)
DEFAULT_THEME_NAME = "Dark Gray"


def _hex_to_rgb(hex_color):
    value = hex_color.strip().lstrip("#")
    if len(value) != 6:
        raise ValueError("Expected 6-digit hex color")
    return tuple(int(value[i:i+2], 16) for i in (0, 2, 4))


def _contrast_text_color(background_hex, fallback_hex="#FFFFFF"):
    try:
        r, g, b = _hex_to_rgb(background_hex)
    except Exception:
        return fallback_hex
    luminance = (0.2126 * r) + (0.7152 * g) + (0.0722 * b)
    return "#FFFFFF" if luminance < 140 else "#000000"


def apply_widget_theme(widget, bg, fg, select_bg=None, select_fg=None):
    if widget is None:
        return
    try:
        widget.configure(bg=bg, fg=fg, insertbackground=fg)
    except Exception:
        pass

    if select_bg is not None or select_fg is not None:
        try:
            widget.configure(selectbackground=select_bg or bg, selectforeground=select_fg or fg)
        except Exception:
            pass


def apply_menu_theme(menu, bg, fg, select_bg, select_fg):
    if menu is None:
        return
    try:
        menu.configure(bg=bg, fg=fg, activebackground=select_bg, activeforeground=select_fg,
                       selectcolor=select_fg, relief="flat", bd=0)
    except Exception:
        pass


@dataclass
class Theme:
    name: str
    colors: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            return None
        name = data.get("name")
        colors = data.get("colors")
        if not name or not isinstance(colors, dict):
            return None
        return cls(name=name, colors=colors)

    def to_dict(self):
        return {"name": self.name, "colors": self.colors}

    def is_valid(self):
        return bool(self.name) and isinstance(self.colors, dict)


class ThemeStore:
    """Manage persisted theme data and active theme selection."""

    def __init__(self, config_path=CONFIG_PATH):
        self.config_path = config_path

    @staticmethod
    def normalize_config(cfg):
        if not isinstance(cfg, dict):
            cfg = {}

        raw_themes = cfg.get("themes", {})
        if not isinstance(raw_themes, dict):
            raw_themes = {}

        valid_themes = {}
        for name, theme_data in raw_themes.items():
            if not isinstance(name, str):
                continue
            if not isinstance(theme_data, dict):
                continue
            parsed = Theme.from_dict(theme_data)
            if parsed is None:
                continue
            valid_themes[name] = parsed.to_dict()

        if not valid_themes:
            fallback = DEFAULT_THEMES.get(DEFAULT_THEME_NAME)
            if fallback:
                valid_themes[DEFAULT_THEME_NAME] = {"name": DEFAULT_THEME_NAME, "colors": fallback}

        cfg["themes"] = valid_themes
        cfg["theme_names"] = list(valid_themes.keys())

        active = cfg.get("active_theme")
        if active not in valid_themes:
            active = cfg["theme_names"][0] if cfg["theme_names"] else None
        cfg["active_theme"] = active
        return cfg

    def ensure_valid_state(self, cfg):
        cfg = self.normalize_config(cfg)
        if not cfg.get("active_theme") and cfg.get("theme_names"):
            cfg["active_theme"] = cfg["theme_names"][0]
        return cfg

    def load(self):
        if not os.path.exists(self.config_path):
            return self.ensure_valid_state({"themes": {}, "active_theme": None, "theme_names": []})

        try:
            with open(self.config_path, "r") as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}

        return self.ensure_valid_state(cfg)

    def save(self, cfg):
        try:
            cfg = self.ensure_valid_state(cfg)
            temp_path = self.config_path + ".tmp"
            with open(temp_path, "w") as f:
                json.dump(cfg, f, indent=4)
            os.replace(temp_path, self.config_path)
            return True
        except Exception as e:
            print("Error saving config:", e)
            return False

    def add_theme(self, cfg, theme_dict):
        theme = Theme.from_dict(theme_dict)
        if theme is None:
            return False

        cfg["themes"][theme.name] = theme.to_dict()
        if theme.name not in cfg["theme_names"]:
            cfg["theme_names"].append(theme.name)
        return self.save(cfg)

    def delete_theme(self, cfg, name):
        if name in cfg.get("themes", {}):
            del cfg["themes"][name]
        if name in cfg.get("theme_names", []):
            cfg["theme_names"].remove(name)
        if cfg.get("active_theme") == name:
            cfg["active_theme"] = None
        return self.save(cfg)

    def rename_theme(self, cfg, old_name, new_name):
        if not old_name or not new_name or old_name == new_name:
            return False
        if old_name not in cfg.get("themes", {}):
            return False
        if new_name in cfg.get("themes", {}):
            return False

        theme = cfg["themes"].pop(old_name)
        cfg["themes"][new_name] = theme

        if old_name in cfg.get("theme_names", []):
            idx = cfg["theme_names"].index(old_name)
            cfg["theme_names"][idx] = new_name
        elif old_name not in cfg["theme_names"]:
            cfg["theme_names"].append(new_name)

        if cfg.get("active_theme") == old_name:
            cfg["active_theme"] = new_name

        return self.save(cfg)

    def set_active_theme(self, cfg, name):
        if name in cfg.get("themes", {}):
            cfg["active_theme"] = name
            return self.save(cfg)
        return False

    def list_themes(self, cfg):
        return list(cfg.get("theme_names", []))

    def get_theme(self, cfg, name):
        return cfg.get("themes", {}).get(name)

    def get_theme_names(self, cfg):
        return self.list_themes(cfg)


class ThemeManager:
    """Apply a theme to the UI with a single public entry point."""

    @staticmethod
    def apply_theme_to_style(root, theme_dict, main_tree=None, value_tree=None,
                            viewer_widget=None, status_label=None, menubar=None):
        if not theme_dict:
            return

        colors = theme_dict.get("colors", {})
        bg = colors.get("background_color", "#202020")
        fg = colors.get("text_color", "#FFFFFF")
        sel = colors.get("selection_color", "#FFCC00")
        accent = colors.get("accent_color", sel)
        accent_text = colors.get("accent_text_color")
        if not accent_text:
            accent_text = colors.get("selection_text_color")
        if not accent_text:
            accent_text = _contrast_text_color(sel, fg)
        row1 = colors.get("treeview_row_color_1", "#1E1E1E")
        row2 = colors.get("treeview_row_color_2", "#252525")
        group_bg = colors.get("group_shading_color", "#e0e0ff")
        menu_bg = colors.get("menu_background_color", bg)
        status_bg = colors.get("status_background_color", bg)

        style = ttk.Style(root)

        try:
            root.configure(bg=bg)
        except Exception:
            pass

        if menubar is not None:
            try:
                menubar.configure(bg=menu_bg)
            except Exception:
                pass

        if status_label is not None:
            try:
                status_label.configure(bg=status_bg, fg=fg)
            except Exception:
                pass

        if viewer_widget is not None:
            apply_widget_theme(viewer_widget, bg, fg, sel, accent_text)

        try:
            style.configure("TFrame", background=bg)
            style.configure("Layout.TLabel", background=bg, foreground=fg, padding=(8, 4), font=("TkDefaultFont", 9, "bold"))
            style.configure("TLabel", background=bg, foreground=fg)
            style.configure("TEntry", fieldbackground=row1, foreground=fg, padding=(4, 2))
            style.configure("TButton", background=bg, foreground=fg, padding=(8, 4))
            style.map("TButton", background=[("active", accent), ("pressed", accent), ("!disabled", bg)], foreground=[("active", accent_text), ("pressed", accent_text), ("!disabled", fg)])
            style.configure("TCombobox", fieldbackground=row1, foreground=fg, background=bg)
            style.map("TCombobox", fieldbackground=[("readonly", row1), ("disabled", row1)], foreground=[("disabled", fg), ("!disabled", fg)], selectbackground=[("readonly", sel)], selectforeground=[("readonly", accent_text)])
            style.configure("Top.TFrame", background=bg)
            style.configure("Top.TLabel", background=bg, foreground=fg, font=("TkDefaultFont", 9, "bold"))
            style.configure("Top.TEntry", fieldbackground=row1, foreground=fg, padding=(4, 2))
            style.configure("Top.TButton", background=bg, foreground=fg, padding=(7, 4))
            style.map("Top.TButton", background=[("active", accent), ("pressed", accent), ("!disabled", bg)], foreground=[("active", accent_text), ("pressed", accent_text), ("!disabled", fg)])
            style.configure("Treeview.Heading", background=bg, foreground=fg, relief="flat", padding=(8, 6), font=("TkDefaultFont", 9, "bold"))
            style.map("Treeview.Heading", background=[("active", sel), ("pressed", sel)], foreground=[("active", accent_text), ("pressed", accent_text)])
            style.configure("Panel.TFrame", background=row1)
            style.configure("PanelBorder.TFrame", background=bg)
            style.configure("Meta.TLabel", background=bg, foreground=fg, padding=(0, 2))

            root.option_add("*TFrame*Background", bg)
            root.option_add("*TLabel*Background", bg)
            root.option_add("*TLabel*Foreground", fg)
            root.option_add("*TEntry*FieldBackground", bg)
            root.option_add("*TEntry*Foreground", fg)
            root.option_add("*TButton*Background", bg)
            root.option_add("*TButton*Foreground", fg)
            root.option_add("*TCombobox*Background", bg)
            root.option_add("*TCombobox*Foreground", fg)
            root.option_add("*TCombobox*Listbox*Background", bg)
            root.option_add("*TCombobox*Listbox*Foreground", fg)
            root.option_add("*TCombobox*Listbox*SelectBackground", sel)
            root.option_add("*TCombobox*Listbox*SelectForeground", accent_text)
            root.option_add("*Menu*Background", menu_bg)
            root.option_add("*Menu*Foreground", fg)
            root.option_add("*Menu*ActiveBackground", sel)
            root.option_add("*Menu*ActiveForeground", accent_text)
            root.option_add("*Listbox*Background", bg)
            root.option_add("*Listbox*Foreground", fg)
            root.option_add("*Listbox*SelectBackground", sel)
            root.option_add("*Listbox*SelectForeground", accent_text)
            root.option_add("*Scrollbar*Background", bg)
            root.option_add("*Scrollbar*TroughColor", bg)
        except Exception:
            pass

        style.configure("Treeview", background=row1, fieldbackground=row1, foreground=fg, rowheight=24, borderwidth=0, relief="flat")
        style.map("Treeview", background=[("selected", sel), ("!disabled", row1)], foreground=[("selected", accent_text), ("!disabled", fg)])

        if main_tree is not None:
            try:
                main_tree.tag_configure("evenrow", background=row1, foreground=fg)
                main_tree.tag_configure("oddrow", background=row2, foreground=fg)
                main_tree.tag_configure("group", background=group_bg, foreground=_contrast_text_color(group_bg, fg), font=("TkDefaultFont", 9, "bold"))
            except Exception:
                pass

        if value_tree is not None:
            try:
                value_tree.tag_configure("evenrow", background=row1, foreground=fg)
                value_tree.tag_configure("oddrow", background=row2, foreground=fg)
            except Exception:
                pass

    @staticmethod
    def apply_active_theme(cfg, root, main_tree=None, value_tree=None,
                          viewer_widget=None, status_label=None, menubar=None):
        cfg = ThemeStore.normalize_config(cfg)
        active_name = cfg.get("active_theme")
        if not active_name:
            return
        theme = ThemeStore().get_theme(cfg, active_name)
        if not theme:
            return
        ThemeManager.apply_theme_to_style(root, theme, main_tree=main_tree,
                                         value_tree=value_tree, viewer_widget=viewer_widget,
                                         status_label=status_label, menubar=menubar)

    @staticmethod
    def apply_default_theme(cfg, root, main_tree=None, value_tree=None,
                            viewer_widget=None, status_label=None, menubar=None):
        cfg = ThemeStore.normalize_config(cfg)
        names = cfg.get("theme_names", [])
        if not names:
            return
        cfg["active_theme"] = names[0]
        ThemeStore().save(cfg)
        theme = ThemeStore().get_theme(cfg, cfg["active_theme"])
        if theme:
            ThemeManager.apply_theme_to_style(root, theme, main_tree=main_tree,
                                             value_tree=value_tree, viewer_widget=viewer_widget,
                                             status_label=status_label, menubar=menubar)

    @staticmethod
    def apply_and_set_active_theme(cfg, name, root, main_tree=None, value_tree=None,
                                  viewer_widget=None, status_label=None, menubar=None):
        theme = ThemeStore().get_theme(cfg, name)
        if not theme:
            return

        ThemeStore().set_active_theme(cfg, name)
        ThemeManager.apply_theme_to_style(root, theme, main_tree=main_tree,
                                         value_tree=value_tree, viewer_widget=viewer_widget,
                                         status_label=status_label, menubar=menubar)


def normalize_config(cfg):
    return ThemeStore.normalize_config(cfg)


def load_config():
    return ThemeStore().load()


def save_config(cfg):
    return ThemeStore().save(cfg)


def add_theme(cfg, theme_dict):
    return ThemeStore().add_theme(cfg, theme_dict)


def delete_theme(cfg, name):
    return ThemeStore().delete_theme(cfg, name)


def rename_theme(cfg, old_name, new_name):
    return ThemeStore().rename_theme(cfg, old_name, new_name)


def set_active_theme(cfg, name):
    return ThemeStore().set_active_theme(cfg, name)


def list_themes(cfg):
    return ThemeStore().list_themes(cfg)


def get_theme(cfg, name):
    return ThemeStore().get_theme(cfg, name)


def validate_theme(theme_dict):
    theme = Theme.from_dict(theme_dict)
    return bool(theme and theme.is_valid())


def apply_theme_to_style(root, theme_dict, main_tree=None, value_tree=None,
                         viewer_widget=None, status_label=None, menubar=None):
    ThemeManager.apply_theme_to_style(root, theme_dict, main_tree=main_tree,
                                     value_tree=value_tree, viewer_widget=viewer_widget,
                                     status_label=status_label, menubar=menubar)


def apply_active_theme(cfg, root, main_tree=None, value_tree=None, viewer_widget=None,
                      status_label=None, menubar=None):
    ThemeManager.apply_active_theme(cfg, root, main_tree=main_tree, value_tree=value_tree,
                                  viewer_widget=viewer_widget, status_label=status_label,
                                  menubar=menubar)


def apply_and_set_active_theme(cfg, name, root, main_tree=None, value_tree=None,
                              viewer_widget=None, status_label=None, menubar=None):
    ThemeManager.apply_and_set_active_theme(cfg, name, root, main_tree=main_tree,
                                          value_tree=value_tree, viewer_widget=viewer_widget,
                                          status_label=status_label, menubar=menubar)


def menu_save_theme(cfg, root,
                    main_tree=None,
                    value_tree=None,
                    viewer_widget=None,
                    status_label=None,
                    menubar=None,
                    color_picker_callback=None):
    """
    Save Theme…
    Behavior:
      - Use color_picker_callback() to get a color dictionary
      - Prefer a selection for existing themes
      - Only prompt for a new name when explicitly creating one
      - Add or update theme via the store
      - Apply theme immediately
    """
    if color_picker_callback is None:
        messagebox.showerror("Save Theme", "No color picker available.")
        return

    colors = color_picker_callback()
    if not colors:
        messagebox.showwarning("Save Theme", "No colors selected.")
        return

    names = list_themes(cfg)
    choices = names + ["Create new theme..."] if names else ["Create new theme..."]
    active_theme = get_theme(cfg, cfg.get("active_theme"))
    theme_colors = active_theme.get("colors", DEFAULT_THEMES.get(DEFAULT_THEME_NAME)) if active_theme else DEFAULT_THEMES.get(DEFAULT_THEME_NAME)
    name = choose_from_list("Save Theme", "Select a theme to overwrite or create a new one:", choices, parent=root, theme_colors=theme_colors)
    if not name:
        return

    if name == "Create new theme...":
        name = simpledialog.askstring("Save Theme", "Enter new theme name:")
        if not name:
            return

    theme_dict = {"name": name, "colors": colors}
    if not validate_theme(theme_dict):
        messagebox.showerror("Save Theme", "Invalid theme data.")
        return

    add_theme(cfg, theme_dict)
    apply_and_set_active_theme(cfg, name, root, main_tree=main_tree,
                              value_tree=value_tree, viewer_widget=viewer_widget,
                              status_label=status_label, menubar=menubar)


def choose_from_list(title, prompt, values, parent=None, theme_colors=None):
    """Open a small themed selection dialog backed by a ttk combobox."""
    if not values:
        return None

    bg = (theme_colors or {}).get("background_color", "#202020")
    fg = (theme_colors or {}).get("text_color", "#E0E0E0")
    sel = (theme_colors or {}).get("selection_color", "#505050")
    accent = (theme_colors or {}).get("accent_color", sel)
    accent_text = (theme_colors or {}).get("accent_text_color") or _contrast_text_color(sel, (theme_colors or {}).get("text_color", "#FFFFFF"))

    win = tk.Toplevel(parent) if parent is not None else tk.Toplevel()
    win.title(title)
    win.geometry("360x140")
    if parent is not None:
        win.transient(parent)
    win.grab_set()
    win.resizable(False, False)
    win.configure(bg=bg)

    dialog_style = ttk.Style(win)
    dialog_style.configure("Dialog.TLabel", background=bg, foreground=fg)
    dialog_style.configure("Dialog.TCombobox", fieldbackground=bg, foreground=fg, background=bg)
    dialog_style.map("Dialog.TCombobox", fieldbackground=[("readonly", bg)], foreground=[("readonly", fg)], selectbackground=[("readonly", accent)], selectforeground=[("readonly", accent_text)])
    dialog_style.configure("Dialog.TButton", background=bg, foreground=fg)
    dialog_style.map("Dialog.TButton", background=[("active", accent), ("pressed", accent), ("!disabled", bg)], foreground=[("active", accent_text), ("pressed", accent_text), ("!disabled", fg)])

    win.option_add("*TCombobox*Listbox*Background", bg)
    win.option_add("*TCombobox*Listbox*Foreground", fg)
    win.option_add("*TCombobox*Listbox*SelectBackground", accent)
    win.option_add("*TCombobox*Listbox*SelectForeground", accent_text)
    win.option_add("*Combobox*Listbox*Background", bg)
    win.option_add("*Combobox*Listbox*Foreground", fg)
    win.option_add("*Combobox*Listbox*SelectBackground", accent)
    win.option_add("*Combobox*Listbox*SelectForeground", accent_text)
    win.option_add("*Listbox*Background", bg)
    win.option_add("*Listbox*Foreground", fg)
    win.option_add("*Listbox*SelectBackground", accent)
    win.option_add("*Listbox*SelectForeground", accent_text)

    ttk.Label(win, text=prompt, style="Dialog.TLabel").pack(padx=16, pady=(12, 6), anchor="w")

    selected = tk.StringVar(value=values[0])
    combo = ttk.Combobox(win, textvariable=selected, values=values, state="readonly", width=32, style="Dialog.TCombobox")
    combo.pack(padx=16, fill="x")

    result = [None]

    def accept():
        result[0] = selected.get()
        win.destroy()

    ttk.Button(win, text="OK", command=accept, style="Dialog.TButton").pack(pady=(10, 12))
    win.wait_window()
    return result[0]


def menu_load_theme(cfg, root,
                    main_tree=None,
                    value_tree=None,
                    viewer_widget=None,
                    status_label=None,
                    menubar=None):
    names = list_themes(cfg)
    if not names:
        messagebox.showinfo("Load Theme", "No themes available.")
        return

    active_theme = get_theme(cfg, cfg.get("active_theme"))
    theme_colors = active_theme.get("colors", DEFAULT_THEMES.get(DEFAULT_THEME_NAME)) if active_theme else DEFAULT_THEMES.get(DEFAULT_THEME_NAME)
    name = choose_from_list("Load Theme", "Select a theme:", names, parent=root, theme_colors=theme_colors)
    if not name or name not in names:
        return

    apply_and_set_active_theme(cfg, name, root, main_tree=main_tree,
                              value_tree=value_tree, viewer_widget=viewer_widget,
                              status_label=status_label, menubar=menubar)


def menu_delete_theme(cfg, root=None, main_tree=None, value_tree=None,
                     viewer_widget=None, status_label=None, menubar=None):
    names = list_themes(cfg)
    if not names:
        messagebox.showinfo("Delete Theme", "No themes available.")
        return

    active_theme = get_theme(cfg, cfg.get("active_theme"))
    theme_colors = active_theme.get("colors", DEFAULT_THEMES.get(DEFAULT_THEME_NAME)) if active_theme else DEFAULT_THEMES.get(DEFAULT_THEME_NAME)
    name = choose_from_list("Delete Theme", "Select a theme to delete:", names, parent=root, theme_colors=theme_colors)
    if not name or name not in names:
        return

    delete_theme(cfg, name)
    if cfg.get("active_theme"):
        apply_active_theme(cfg, root, main_tree=main_tree, value_tree=value_tree,
                          viewer_widget=viewer_widget, status_label=status_label,
                          menubar=menubar)
    elif root is not None:
        ThemeManager.apply_default_theme(cfg, root, main_tree=main_tree,
                                        value_tree=value_tree, viewer_widget=viewer_widget,
                                        status_label=status_label, menubar=menubar)

    messagebox.showinfo("Delete Theme", f"Theme '{name}' deleted.")


def menu_edit_theme(cfg, root,
                    main_tree=None,
                    value_tree=None,
                    viewer_widget=None,
                    status_label=None,
                    menubar=None,
                    color_picker_callback=None):
    names = list_themes(cfg)
    if not names:
        messagebox.showinfo("Edit Theme", "No themes available.")
        return

    active_theme = get_theme(cfg, cfg.get("active_theme"))
    theme_colors = active_theme.get("colors", DEFAULT_THEMES.get(DEFAULT_THEME_NAME)) if active_theme else DEFAULT_THEMES.get(DEFAULT_THEME_NAME)
    name = choose_from_list("Edit Theme", "Select a theme to edit:", names, parent=root, theme_colors=theme_colors)
    if not name or name not in names:
        return

    theme = get_theme(cfg, name)
    if not theme:
        messagebox.showerror("Edit Theme", "Theme not found.")
        return

    if color_picker_callback is None:
        messagebox.showerror("Edit Theme", "No color picker available.")
        return

    new_colors = color_picker_callback(initial_colors=theme.get("colors"))
    if not new_colors:
        return

    updated_theme = {"name": name, "colors": new_colors}
    if not validate_theme(updated_theme):
        messagebox.showerror("Edit Theme", "Invalid theme data.")
        return

    add_theme(cfg, updated_theme)
    apply_and_set_active_theme(cfg, name, root, main_tree=main_tree,
                              value_tree=value_tree, viewer_widget=viewer_widget,
                              status_label=status_label, menubar=menubar)

# ------------------------------------------------------------
# Parse a single .fad layout line (fixed-width columns)
# ------------------------------------------------------------
def parse_layout_line(line):
    if len(line) < 70:
        return None

    level = line[0:5].strip()
    name  = line[6:31].strip()
    pic   = line[31:41].strip()
    fld   = line[41:46].strip()
    start = line[46:54].strip()
    end   = line[54:62].strip()

    if not level.isdigit():
        return None

    return {
        "level": int(level),
        "name": name,
        "pic": pic,
        "fld": int(fld) if fld else 0,
        "start": int(start),
        "end": int(end),
        "type": line[70:].strip().upper() if len(line) > 70 else "",
    }
# ------------------------------------------------------------
# Load .fad layout file
# ------------------------------------------------------------
def load_layout_file(path):
    path = os.fspath(path)
    if not os.path.isabs(path):
        path = os.path.join(APP_DIRECTORY, path)

    fields = []
    with open(path, "r") as f:
        lines = f.readlines()

    lines = lines[2:]  # skip header + blank line

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        field = parse_layout_line(line)
        if field:
            fields.append(field)

    return fields
# ------------------------------------------------------------
# Load data file (binary)
# ------------------------------------------------------------
def load_data_file(path):
    with open(path, "rb") as f:
        data = f.read()

    data = data.replace(b"\r", b"").replace(b"\n", b"")
    return bytearray(data)


def load_data_records(path):
    with open(path, "rb") as data_file:
        data = data_file.read()
    return [bytearray(record) for record in data.splitlines() if record]


def select_layout_for_record(record, config):
    if config.get("mode", "single") == "single":
        return None

    key_start = int(config.get("key_start", 1)) - 1
    key_length = int(config.get("key_length", 1))
    if key_start < 0 or key_length <= 0:
        return None

    key_value = record[key_start:key_start + key_length]
    if isinstance(key_value, (bytes, bytearray)):
        key = key_value.decode("utf-8", errors="replace").strip()
    else:
        key = str(key_value).strip()

    mappings = {
        str(mapping["key"]): mapping["layout"]
        for mapping in config.get("mappings", [])
        if isinstance(mapping, dict) and "key" in mapping and "layout" in mapping
    }
    return mappings.get(key)
# ------------------------------------------------------------
# Extract field value from record
# ------------------------------------------------------------
def extract_field_value(data, record_length, record_index, field):
    if record_length <= 0:
        return ""

    start = field["start"] - 1
    end   = field["end"]
    length = end - start

    offset = record_index * record_length + start
    if offset < 0 or offset + length > len(data):
        return ""

    raw = data[offset:offset + length]

    try:
        text = raw.decode("utf-8", errors="replace")
    except Exception:
        text = raw.decode("latin-1", errors="replace")

    return text.rstrip()
def menu_rename_theme(cfg, root=None, main_tree=None, value_tree=None,
                     viewer_widget=None, status_label=None, menubar=None):
    """Choose the old theme from a dropdown and type in the new name."""
    import tkinter.messagebox as mb

    names = list_themes(cfg)
    if not names:
        mb.showinfo("Rename Theme", "No themes available.")
        return

    active_theme = get_theme(cfg, cfg.get("active_theme"))
    theme_colors = active_theme.get("colors", DEFAULT_THEMES.get(DEFAULT_THEME_NAME)) if active_theme else DEFAULT_THEMES.get(DEFAULT_THEME_NAME)
    old_name = choose_from_list("Rename Theme", "Select the theme to rename:", names, parent=root, theme_colors=theme_colors)
    if not old_name or old_name not in cfg.get("themes", {}):
        return

    new_name = simpledialog.askstring("Rename Theme", "Enter the NEW theme name:")
    if not new_name:
        return

    if new_name in cfg.get("themes", {}):
        mb.showerror("Rename Theme", f"Theme '{new_name}' already exists.")
        return

    rename_theme(cfg, old_name, new_name)
    if root is not None and cfg.get("active_theme"):
        apply_active_theme(cfg, root, main_tree=main_tree, value_tree=value_tree,
                          viewer_widget=viewer_widget, status_label=status_label,
                          menubar=menubar)
    mb.showinfo("Rename Theme", f"Theme renamed to '{new_name}'.")
# ------------------------------------------------------------
# Part 5: Color Picker Dialog (Add-only implementation)
# ------------------------------------------------------------
def pick_color(title, initial):
    """
    Helper: open a color chooser dialog.
    Returns a hex color string or the initial value if cancelled.
    """
    import tkinter.colorchooser as cc
    color = cc.askcolor(title=title, color=initial)
    if color and color[1]:
        return color[1]
    return initial
def pick_theme_colors(initial_colors=None):
    """
    Interactive color picker for all theme colors.
    Returns a complete theme color dictionary.
    """
    if initial_colors is None:
        initial_colors = {}

    # Default values if missing
    bg = initial_colors.get("background_color", "#202020")
    fg = initial_colors.get("text_color", "#FFFFFF")
    sel = initial_colors.get("selection_color", "#FFCC00")
    accent_text = initial_colors.get("accent_text_color") or initial_colors.get("selection_text_color") or _contrast_text_color(sel, fg)
    row1 = initial_colors.get("treeview_row_color_1", "#1E1E1E")
    row2 = initial_colors.get("treeview_row_color_2", "#252525")
    group_bg = initial_colors.get("group_shading_color", "#303040")
    pic_color = initial_colors.get("pic_type_color", "#66CCFF")
    menu_bg = initial_colors.get("menu_background_color", bg)
    status_bg = initial_colors.get("status_background_color", bg)

    # Pick each color interactively
    bg = pick_color("Background Color", bg)
    fg = pick_color("Text Color", fg)
    sel = pick_color("Selection Background Color", sel)
    accent_text = pick_color("Selected Text Color", accent_text)
    row1 = pick_color("Treeview Row Color 1", row1)
    row2 = pick_color("Treeview Row Color 2", row2)
    group_bg = pick_color("Group Shading Color", group_bg)
    pic_color = pick_color("PIC Type Color", pic_color)
    menu_bg = pick_color("Menu Background Color", menu_bg)
    status_bg = pick_color("Status Background Color", status_bg)

    return {
        "background_color": bg,
        "text_color": fg,
        "selection_color": sel,
        "accent_color": sel,
        "accent_text_color": accent_text,
        "selection_text_color": accent_text,
        "treeview_row_color_1": row1,
        "treeview_row_color_2": row2,
        "group_shading_color": group_bg,
        "pic_type_color": pic_color,
        "menu_background_color": menu_bg,
        "status_background_color": status_bg
    }
# ------------------------------------------------------------
# Part 6: Apply theme to top controls (ttk widgets)
# ------------------------------------------------------------
def apply_theme_to_top_controls(root, colors):
    """
    Recolors the top controls (ttk Frame, ttk Label, ttk Entry, ttk Button)
    using ttk Style so that custom themes affect the entire top bar.
    """

    style = ttk.Style(root)

    bg = colors["background_color"]
    fg = colors["text_color"]

    # Frame background
    style.configure("Top.TFrame", background=bg)

    # Label styling
    style.configure("Top.TLabel", background=bg, foreground=fg)

    # Entry styling
    style.configure("Top.TEntry", fieldbackground=bg, foreground=fg)

    # Button styling
    style.configure("Top.TButton", background=bg, foreground=fg)
    style.configure("Treeview.Heading", background=bg, foreground=fg, relief="flat", padding=(6, 4))

    # Apply styles globally to your top widgets
    root.option_add("*TFrame*Background", bg)
    root.option_add("*TLabel*Background", bg)
    root.option_add("*TLabel*Foreground", fg)
    root.option_add("*TEntry*FieldBackground", bg)
    root.option_add("*TEntry*Foreground", fg)
    root.option_add("*TButton*Background", bg)
    root.option_add("*TButton*Foreground", fg)

DEFAULT_THEMES = {
    "Dark Gray": {
        "background_color": "#1B1B1B",
        "text_color": "#EAEAEA",
        "selection_color": "#4A7DB8",
        "accent_color": "#4A7DB8",
        "accent_text_color": "#FFFFFF",
        "selection_text_color": "#FFFFFF",
        "treeview_row_color_1": "#262626",
        "treeview_row_color_2": "#313131",
        "group_shading_color": "#3A4461",
        "pic_type_color": "#7DD3FC",
        "menu_background_color": "#1B1B1B",
        "status_background_color": "#1B1B1B",
    },
    "Dark Blue": {
        "background_color": "#101C2A",
        "text_color": "#E6F1FF",
        "selection_color": "#2E6FCD",
        "accent_color": "#2E6FCD",
        "accent_text_color": "#FFFFFF",
        "selection_text_color": "#FFFFFF",
        "treeview_row_color_1": "#1A2A3A",
        "treeview_row_color_2": "#233448",
        "group_shading_color": "#35567A",
        "pic_type_color": "#7DD3FC",
        "menu_background_color": "#101C2A",
        "status_background_color": "#101C2A",
    },
    "Light": {
        "background_color": "#F3F3F3",
        "text_color": "#111111",
        "selection_color": "#B5D6FF",
        "accent_color": "#B5D6FF",
        "accent_text_color": "#111111",
        "selection_text_color": "#111111",
        "treeview_row_color_1": "#FFFFFF",
        "treeview_row_color_2": "#F3F6FA",
        "group_shading_color": "#D7E7FF",
        "pic_type_color": "#3AA0FF",
        "menu_background_color": "#F3F3F3",
        "status_background_color": "#F3F3F3",
    },
    "Light Blue": {
        "background_color": "#EAF3FF",
        "text_color": "#111111",
        "selection_color": "#9CC7FF",
        "accent_color": "#9CC7FF",
        "accent_text_color": "#111111",
        "selection_text_color": "#111111",
        "treeview_row_color_1": "#F2F8FF",
        "treeview_row_color_2": "#E5F0FF",
        "group_shading_color": "#CBE0FF",
        "pic_type_color": "#2D8CFF",
        "menu_background_color": "#EAF3FF",
        "status_background_color": "#EAF3FF",
    },
    "Blackout": {
        "background_color": "#000000",
        "text_color": "#F5F5F5",
        "selection_color": "#2E6FCD",
        "accent_color": "#2E6FCD",
        "accent_text_color": "#FFFFFF",
        "selection_text_color": "#FFFFFF",
        "treeview_row_color_1": "#121212",
        "treeview_row_color_2": "#1B1B1B",
        "group_shading_color": "#2B2F3B",
        "pic_type_color": "#7DD3FC",
        "menu_background_color": "#000000",
        "status_background_color": "#000000",
    },
}


def open_copybook_layout_window():
    root = tk._default_root
    if root is None:
        return

    modal = tk.Toplevel(root)
    modal.title("Generate Layout")
    modal.transient(root)
    modal.grab_set()
    modal.resizable(False, False)
    modal.configure(bg="#f0f0f0")

    modal.update_idletasks()
    screen_w = modal.winfo_screenwidth()
    screen_h = modal.winfo_screenheight()
    width = 760
    height = 520
    x = (screen_w - width) // 2
    y = (screen_h - height) // 2
    modal.geometry(f"{width}x{height}+{x}+{y}")

    tool = CopybookToLayout(modal)
    tool.pack(fill="both", expand=True)
    modal.wait_window()


def open_key_definition_dialog():
    root = tk._default_root
    if root is None:
        return

    modal = tk.Toplevel(root)
    modal.title("Key Definition")
    modal.transient(root)
    modal.grab_set()
    modal.resizable(False, False)

    modal.update_idletasks()
    w = 600
    h = 500
    x = (modal.winfo_screenwidth() // 2) - (w // 2)
    y = (modal.winfo_screenheight() // 2) - (h // 2)
    modal.geometry(f"{w}x{h}+{x}+{y}")

    build_key_definition_ui(modal)
    modal.wait_window()


def save_key_definition(mode, key_start, key_length, mappings):
    data = {
        "mode": mode,
        "key_start": key_start,
        "key_length": key_length,
        "mappings": mappings,
    }
    with open(KEY_DEFINITION_CONFIG_FILE, "w", encoding="utf-8") as config_file:
        json.dump(data, config_file, indent=4)


def _layout_filename(path):
    path = os.fspath(path)
    if os.path.isabs(path):
        candidate_path = path
    elif os.path.dirname(path):
        candidate_path = os.path.join(APP_DIRECTORY, path)
    else:
        candidate_path = os.path.join(LAYOUT_DIR, path)
    absolute_path = os.path.realpath(candidate_path)
    layout_directory = os.path.realpath(LAYOUT_DIR)
    if os.path.dirname(absolute_path) != layout_directory:
        return None
    if os.path.splitext(absolute_path)[1].lower() != ".fad":
        return None
    return os.path.basename(absolute_path)


def get_available_layout_files():
    layout_files = []
    for path in sorted(glob.glob(os.path.join(LAYOUT_DIR, "*.fad"))):
        filename = _layout_filename(path)
        if filename:
            layout_files.append(filename)
    return layout_files


def load_key_definition():
    defaults = {
        "mode": "single",
        "key_start": 1,
        "key_length": 1,
        "mappings": [],
    }
    if not os.path.exists(KEY_DEFINITION_CONFIG_FILE):
        return defaults

    try:
        with open(KEY_DEFINITION_CONFIG_FILE, "r", encoding="utf-8") as config_file:
            config = json.load(config_file)
    except (OSError, json.JSONDecodeError):
        return defaults

    if not isinstance(config, dict):
        return defaults
    if config.get("mode") not in ("single", "key"):
        config["mode"] = defaults["mode"]
    for field in ("key_start", "key_length"):
        try:
            config[field] = int(config.get(field, defaults[field]))
        except (TypeError, ValueError):
            config[field] = defaults[field]
    if not isinstance(config.get("mappings"), list):
        config["mappings"] = defaults["mappings"]
    config["mappings"] = [
        {"key": item["key"], "layout": filename}
        for item in config["mappings"]
        if isinstance(item, dict)
        and "key" in item
        and "layout" in item
        and (filename := _layout_filename(item["layout"]))
    ]
    return config


def build_key_definition_ui(parent):
    """Build the key-based layout switching dialog."""
    frame = ttk.Frame(parent)
    frame.pack(fill="both", expand=True, padx=10, pady=10)

    config = load_key_definition()
    mode_var = tk.StringVar(parent, value=config["mode"])
    key_start_var = tk.StringVar(parent, value=str(config["key_start"]))
    key_length_var = tk.StringVar(parent, value=str(config["key_length"]))

    ttk.Label(frame, text="Mode:").grid(row=0, column=0, sticky="w", padx=5, pady=(0, 6))
    ttk.Radiobutton(frame, text="Single Layout Mode", variable=mode_var, value="single").grid(
        row=0, column=1, sticky="w", padx=(0, 12), pady=(0, 6)
    )
    ttk.Radiobutton(frame, text="Key Selector Mode", variable=mode_var, value="key").grid(
        row=0, column=2, sticky="w", padx=(0, 12), pady=(0, 6)
    )

    ttk.Label(frame, text="Key Start Position:").grid(row=1, column=0, sticky="w", padx=5, pady=4)
    ttk.Entry(frame, textvariable=key_start_var, width=12).grid(
        row=1, column=1, sticky="w", padx=(0, 12), pady=4
    )

    ttk.Label(frame, text="Key Length:").grid(row=1, column=2, sticky="w", padx=5, pady=4)
    ttk.Entry(frame, textvariable=key_length_var, width=12).grid(
        row=1, column=3, sticky="w", pady=4
    )

    tree = ttk.Treeview(frame, columns=("key", "layout"), show="headings", height=12)
    tree.heading("key", text="Key")
    tree.heading("layout", text="Layout")
    tree.column("key", width=140, anchor="center")
    tree.column("layout", width=300)
    tree.grid(row=2, column=0, columnspan=4, sticky="nsew", padx=5, pady=(10, 6))
    for item in config["mappings"]:
        tree.insert("", "end", values=(item["key"], item["layout"]))

    available_layouts = get_available_layout_files()
    layout_var = tk.StringVar(parent)
    ttk.Label(frame, text="Existing layouts:").grid(row=3, column=0, sticky="w", padx=5, pady=4)
    layout_dropdown = ttk.Combobox(
        frame, textvariable=layout_var, values=available_layouts, state="readonly"
    )
    layout_dropdown.grid(row=3, column=1, columnspan=3, sticky="ew", padx=5, pady=4)
    if available_layouts:
        layout_dropdown.set(available_layouts[0])

    button_row = ttk.Frame(frame)
    button_row.grid(row=4, column=0, columnspan=4, sticky="w", padx=5, pady=(0, 10))

    def add_key():
        key = simpledialog.askstring("Add Key", "Enter key value:", parent=parent)
        if key is None:
            return
        key = key.strip()
        if not key:
            status_var.set("Key value cannot be blank.")
            return
        if any(str(tree.item(row, "values")[0]) == key for row in tree.get_children()):
            status_var.set(f"Key '{key}' already exists.")
            return
        tree.insert("", "end", values=(key, ""))
        status_var.set(f"Added key: {key}")

    def remove_key():
        selected = tree.selection()
        if not selected:
            status_var.set("Select a key to remove.")
            return
        for row in selected:
            tree.delete(row)
        status_var.set("Selected key removed.")

    def assign_layout(layout_name, status_prefix):
        selected = tree.selection()
        if not selected:
            status_var.set("Select a key first.")
            return
        if not layout_name:
            status_var.set("No layout selected.")
            return
        filename = _layout_filename(layout_name)
        if not filename:
            status_var.set(f"Choose a .fad file from {os.path.basename(LAYOUT_DIR)}.")
            return
        key = tree.item(selected[0], "values")[0]
        tree.item(selected[0], values=(key, filename))
        status_var.set(f"{status_prefix}: {filename}")

    def on_apply_layout():
        assign_layout(layout_var.get(), "Applied layout")

    ttk.Button(button_row, text="Add Key", command=add_key).pack(side="left", padx=(0, 6))
    ttk.Button(button_row, text="Remove Key", command=remove_key).pack(side="left", padx=(0, 6))
    ttk.Button(button_row, text="Apply Layout", command=on_apply_layout).pack(side="left")

    footer = ttk.Frame(frame)
    footer.grid(row=5, column=0, columnspan=4, sticky="ew", padx=5)

    status_var = tk.StringVar(value="Ready")
    ttk.Label(footer, textvariable=status_var, anchor="w").pack(side="left", fill="x", expand=True)

    def on_save():
        try:
            key_start = int(key_start_var.get())
            key_length = int(key_length_var.get())
            mappings = []
            for row in tree.get_children():
                key, layout = tree.item(row)["values"]
                mappings.append({"key": key, "layout": layout})
            save_key_definition(mode_var.get(), key_start, key_length, mappings)
        except ValueError:
            status_var.set("Key start position and length must be integers.")
            return
        except OSError as error:
            status_var.set(f"Could not save configuration: {error}")
            return

        status_var.set("Saved successfully.")
        parent.destroy()

    ttk.Button(footer, text="Save", command=on_save).pack(side="right", padx=(6, 0))
    ttk.Button(footer, text="Close", command=parent.destroy).pack(side="right")

    frame.columnconfigure(3, weight=1)
    frame.rowconfigure(2, weight=1)


# ------------------------------------------------------------
# Main UI
# ------------------------------------------------------------
class FileAidViewer:
    # --------------------------------------------------------
    # Theme handling
    # --------------------------------------------------------
    def apply_theme_dict(self, colors):
        theme = {"name": "Custom", "colors": colors}
        ThemeManager.apply_theme_to_style(
            self.root,
            theme,
            main_tree=self.tree,
            value_tree=self.value_tree,
            viewer_widget=self.edit_box,
            status_label=self.status_label,
            menubar=self.menubar,
        )

    def apply_theme_preset(self, theme_name):
        colors = DEFAULT_THEMES.get(theme_name)
        if not colors:
            return
        self.apply_theme_dict(colors)

    def set_dark_gray_theme(self):
        self.apply_theme_preset("Dark Gray")

    def set_dark_blue_theme(self):
        self.apply_theme_preset("Dark Blue")

    def set_light_theme(self):
        self.apply_theme_preset("Light")

    def set_light_blue_theme(self):
        self.apply_theme_preset("Light Blue")

    def set_blackout_theme(self):
        self.apply_theme_preset("Blackout")

    def pick_custom_theme(self):
        bg_color = colorchooser.askcolor(title="Background color")[1]
        if not bg_color:
            return
        fg_color = colorchooser.askcolor(title="Foreground color")[1]
        if not fg_color:
            return
        tree_bg = colorchooser.askcolor(title="Tree background")[1]
        if not tree_bg:
            return
        tree_fg = colorchooser.askcolor(title="Tree foreground")[1]
        if not tree_fg:
            return
        select_bg = colorchooser.askcolor(title="Selection background")[1]
        if not select_bg:
            return

        self.apply_theme_dict({
            "background_color": bg_color,
            "text_color": fg_color,
            "selection_color": select_bg,
            "treeview_row_color_1": tree_bg,
            "treeview_row_color_2": tree_bg,
            "group_shading_color": tree_bg,
            "pic_type_color": "#66CCFF",
            "menu_background_color": bg_color,
            "status_background_color": bg_color,
        })
    def perform_find(self, search_text):
        if not search_text or self.record_length <= 0 or not self.layout:
            return

        search_text_lower = search_text.lower()

        if self.key_mode:
            for offset in range(self.total_records):
                record_index = (self.current_record + offset) % self.total_records
                record = self.records[record_index]
                layout_path = select_layout_for_record(record, load_key_definition())
                search_layout = self.layout
                if layout_path:
                    filename = _layout_filename(layout_path)
                    if filename:
                        try:
                            search_layout = load_layout_file(os.path.join(LAYOUT_DIR, filename))
                        except (OSError, ValueError):
                            continue

                for field_index, field in enumerate(search_layout):
                    value = extract_field_value(record, len(record), 0, field)
                    if search_text_lower in value.lower():
                        self.current_record = record_index
                        self._apply_key_layout_for_current_record()
                        self.record_entry.delete(0, tk.END)
                        self.record_entry.insert(0, str(record_index + 1))
                        self.update_record_count()
                        self.refresh_values()
                        item = self.tree.get_children()[field_index]
                        self.tree.selection_set(item)
                        self.tree.see(item)
                        self.edit_box.delete("1.0", tk.END)
                        self.edit_box.insert("1.0", value)
                        return
            tk.messagebox.showinfo("Find", f"'{search_text}' not found.")
            return

        # Search from current record forward, then wrap
        start_rec = self.current_record
        total = self.total_records

        for i in range(total):
            rec = (start_rec + i) % total

            # Check each field in the record
            for f in self.layout:
                val = extract_field_value(self.data, self.record_length, rec, f)
                if search_text_lower in val.lower():
                    # Found match
                    self.current_record = rec

                    # Update UI
                    self.record_entry.delete(0, tk.END)
                    self.record_entry.insert(0, str(rec + 1))
                    self.update_record_count()
                    self.refresh_values()

                    # Select the field in the left tree
                    idx = self.layout.index(f)
                    item = self.tree.get_children()[idx]
                    self.tree.selection_set(item)
                    self.tree.see(item)

                    # Load into edit box
                    self.edit_box.delete("1.0", tk.END)
                    self.edit_box.insert("1.0", val)

                    return

        # If nothing found
        tk.messagebox.showinfo("Find", f"'{search_text}' not found.")
    def find_value(self):
        win = tk.Toplevel(self.root)
        win.title("Find")
        win.geometry("300x120")
        win.resizable(False, False)

        ttk.Label(win, text="Find text:").pack(pady=5)

        entry = ttk.Entry(win, width=30)
        entry.pack(pady=5)
        entry.focus()
        def do_find():
            text = entry.get()
            win.destroy()
            self.perform_find(text)

        ttk.Button(win, text="Find", command=do_find).pack(pady=5)
    def __init__(self, root):
        self.root = root
        self.theme_store = ThemeStore()
        self.config = self.theme_store.load()
        self.status_label = tk.Label(self.root, text="", anchor="w")
        self.status_label.pack(fill="x", side="bottom")

        self.root.title("PC FileAid Viewer")
        self.root.minsize(860, 520)

        self.layout_name_var = tk.StringVar(value="Layout: (none)")
        self.layout_name_label = ttk.Label(self.root, textvariable=self.layout_name_var, anchor="w", style="Layout.TLabel")
        self.layout_name_label.pack(fill="x", padx=10, pady=(8, 3))

        self.layout = []
        self.data = bytearray()
        self.records = []
        self.key_mode = False
        self.record_length = 0
        self.current_record = 0
        self.data_file_path = None
        self.current_layout_path = None
        self.total_records = 0
        self.binary_lab_window = None

        frame = ttk.Frame(root)
        frame.pack(fill="both", expand=True)

        # --------------------------------------------------------
        # TOP CONTROLS
        # --------------------------------------------------------
        top = ttk.Frame(frame, style="Top.TFrame")
        top.pack(fill="x", padx=8, pady=(6, 4))

        panel_sep = ttk.Frame(frame, height=2, style="PanelBorder.TFrame")
        panel_sep.pack(fill="x", padx=8, pady=(0, 5))

        ttk.Label(top, text="Record:", style="Top.TLabel").pack(side="left", padx=(2, 6))

        self.record_entry = ttk.Entry(top, width=6, style="Top.TEntry")
        self.record_entry.pack(side="left", padx=(0, 4))
        self.record_entry.insert(0, "1")

        self.prev_button = ttk.Button(top, text="Prev",
                                      command=self.prev_record,
                                      style="Top.TButton")
        self.prev_button.pack(side="left", padx=(0, 4))

        self.next_button = ttk.Button(top, text="Next",
                                      command=self.next_record,
                                      style="Top.TButton")
        self.next_button.pack(side="left", padx=(0, 6))

        self.record_label = ttk.Label(top, text="Record 0 of 0", style="Top.TLabel")
        self.record_label.pack(side="left", padx=(0, 10))

        # Data file name display
        self.filename_label = ttk.Label(top, text="No data file loaded", style="Top.TLabel")
        self.filename_label.pack(side="right", padx=10)
        self.filename_label.configure(anchor="e")


        # --------------------------------------------------------
        # JUMP-TO-RECORD CONTROLS
        # --------------------------------------------------------
        jump_frame = ttk.Frame(top, style="Panel.TFrame")
        jump_frame.pack(side="left", padx=(20, 6), pady=2)

        ttk.Label(jump_frame, text="Jump to:", style="Top.TLabel").pack(side="left", padx=(0, 4))

        self.jump_entry = ttk.Entry(jump_frame, width=8, style="Top.TEntry")
        self.jump_entry.pack(side="left", padx=(0, 4))

        ttk.Button(jump_frame, text="Go", command=self.jump_to_record, style="Top.TButton").pack(side="left")

        # --------------------------------------------------------
        # SPLIT PANE
        # --------------------------------------------------------
        paned = ttk.Panedwindow(frame, orient="horizontal")
        paned.pack(fill="both", expand=True)

        # LEFT PANE (LAYOUT)
        left_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=1)

        self.tree = ttk.Treeview(
            left_frame,
            columns=("level", "name", "pic", "start", "end"),
            show="headings"
        )

        self.tree.heading("level", text="FIELD LEVEL")
        self.tree.heading("name",  text="FIELD NAME")
        self.tree.heading("pic",   text="PICTURE")
        self.tree.heading("start", text="FLD START")
        self.tree.heading("end",   text="FLD END")

        self.tree.column("level", width=80)
        self.tree.column("name",  width=220)
        self.tree.column("pic",   width=100)
        self.tree.column("start", width=80)
        self.tree.column("end",   width=80)

        self.tree.tag_configure("group", background="#e0e0ff")

        tree_scroll = ttk.Scrollbar(left_frame, orient="vertical", command=self._scroll_both)
        self.tree.configure(yscrollcommand=tree_scroll.set)

        self.tree.pack(side="left", fill="both", expand=True)
        tree_scroll.pack(side="right", fill="y")

        # RIGHT PANE (VALUES)
        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=1)

        self.value_tree = ttk.Treeview(
            right_frame,
            columns=("value",),
            show="headings"
        )
        self.value_tree.heading("value", text="VALUE")
        self.value_tree.column("value", width=400)

        value_scroll = ttk.Scrollbar(right_frame, orient="vertical", command=self._scroll_both)
        self.value_tree.configure(yscrollcommand=value_scroll.set)

        self.value_tree.pack(side="left", fill="both", expand=True)
        value_scroll.pack(side="right", fill="y")

        # --------------------------------------------------------
        # EDIT BOX + RULER (correct placement)
        # --------------------------------------------------------
        bottom = ttk.Frame(frame, style="Panel.TFrame")
        bottom.pack(fill="x", padx=8, pady=(6, 8))

        # Left column: label
        label_frame = ttk.Frame(bottom)
        label_frame.pack(side="left", padx=(0, 8), anchor="n")
        ttk.Label(label_frame, text="Edit field value:").pack()

        # Right column: ruler + textbox
        edit_frame = ttk.Frame(bottom)
        edit_frame.pack(side="left", fill="x", expand=True, padx=(0, 6))

        # Ruler directly above textbox
        self.ruler = tk.Text(edit_frame, height=1, font=("Courier New", 10), bd=0)
        self.ruler.pack(fill="x")
        self.ruler.config(state="disabled")

        # Make ruler truly non-editable and non-focusable
        self.ruler.bind("<Key>", lambda e: "break")
        self.ruler.bind("<Button-1>", lambda e: "break")

        # Textbox
        self.edit_box = tk.Text(edit_frame, height=3, font=("Courier New", 10))
        self.edit_box.pack(fill="x", expand=True)

        self.apply_button = ttk.Button(bottom, text="Apply", command=self.apply_edit)
        self.apply_button.pack(side="left", padx=(4, 0))

        self.tree.bind("<<TreeviewSelect>>", self.on_field_select)
        self.value_tree.bind("<<TreeviewSelect>>", self.on_field_select)

        # Keep both panes aligned when the mouse wheel is used.
        for widget in (self.tree, self.value_tree):
            widget.bind("<MouseWheel>", self._on_mouse_wheel)
            widget.bind("<Button-4>", self._on_mouse_wheel)
            widget.bind("<Button-5>", self._on_mouse_wheel)

        # --------------------------------------------------------
        # MENU
        # --------------------------------------------------------
        self.menubar = tk.Menu(self.root)
        self.root.config(menu=self.menubar)

        menu_bar = self.menubar
        layouts_menu = tk.Menu(menu_bar, tearoff=0)
        layouts_menu.add_command(label="Generate Layout…", command=open_copybook_layout_window)
        layouts_menu.add_command(label="Key Definition…", command=open_key_definition_dialog)
        menu_bar.add_cascade(label="Layouts", menu=layouts_menu)

        filemenu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label="File", menu=filemenu)

        tools_menu = tk.Menu(self.menubar, tearoff=0)
        tools_menu.add_command(label="Binary Lab...", command=self.open_binary_lab)
        self.menubar.add_cascade(label="Tools", menu=tools_menu)

        thememenu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label="Theme", menu=thememenu)

        self.menu_widgets = [self.menubar, layouts_menu, filemenu, tools_menu, thememenu]

        thememenu.add_command(
            label="Save Theme…",
            command=lambda: menu_save_theme(
                self.config,
                self.root,
                main_tree=self.tree,
                value_tree=self.value_tree,
                viewer_widget=self.edit_box,
                status_label=self.status_label,
                menubar=self.menubar,
                color_picker_callback=self.get_custom_colors
            )
        )

        thememenu.add_command(
            label="Load Theme…",
            command=lambda: menu_load_theme(
                self.config,
                self.root,
                main_tree=self.tree,
                value_tree=self.value_tree,
                viewer_widget=self.edit_box,
                status_label=self.status_label,
                menubar=self.menubar
            )
        )

        thememenu.add_command(
            label="Delete Theme…",
            command=lambda: menu_delete_theme(
                self.config,
                self.root,
                main_tree=self.tree,
                value_tree=self.value_tree,
                viewer_widget=self.edit_box,
                status_label=self.status_label,
                menubar=self.menubar,
            )
        )

        thememenu.add_command(
            label="Edit Theme…",
            command=lambda: menu_edit_theme(
                self.config,
                self.root,
                main_tree=self.tree,
                value_tree=self.value_tree,
                viewer_widget=self.edit_box,
                status_label=self.status_label,
                menubar=self.menubar,
                color_picker_callback=self.get_custom_colors
            )
        )
        thememenu.add_command(
            label="Rename Theme…",
            command=lambda: menu_rename_theme(
                self.config,
                self.root,
                main_tree=self.tree,
                value_tree=self.value_tree,
                viewer_widget=self.edit_box,
                status_label=self.status_label,
                menubar=self.menubar,
            )
        )

        thememenu.add_command(
            label="Default Theme",
            command=lambda: ThemeManager.apply_default_theme(
                self.config,
                self.root,
                main_tree=self.tree,
                value_tree=self.value_tree,
                viewer_widget=self.edit_box,
                status_label=self.status_label,
                menubar=self.menubar,
            )
        )

        filemenu.add_command(label="Open Layout (.fad)", command=self.open_layout)
        filemenu.add_command(label="Open Data File", command=self.open_data)
        filemenu.add_command(label="New Data File", command=self.new_data_file)
        filemenu.add_separator()
        filemenu.add_command(label="Save Data File", command=self.save_data_file)
        filemenu.add_command(label="Save Data File As...", command=self.save_data_file_as)
        filemenu.add_separator()
        filemenu.add_command(label="Exit", command=self.root.destroy)

        editmenu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label="Edit", menu=editmenu)
        self.menu_widgets.append(editmenu)

        editmenu.add_command(label="Insert Record", command=self.insert_record)
        editmenu.add_command(label="Delete Record", command=self.delete_record)
        editmenu.add_command(label="Find...", command=self.find_value)

        if self.config.get("active_theme"):
            apply_active_theme(
                self.config,
                self.root,
                main_tree=self.tree,
                value_tree=self.value_tree,
                viewer_widget=self.edit_box,
                status_label=self.status_label,
                menubar=self.menubar,
            )

        self._apply_menu_theme_colors()

    def _apply_menu_theme_colors(self):
        theme = self.config.get("themes", {}).get(self.config.get("active_theme"))
        colors = (theme or {}).get("colors", DEFAULT_THEMES.get(DEFAULT_THEME_NAME, {}))
        bg = colors.get("background_color", "#202020")
        fg = colors.get("text_color", "#E0E0E0")
        sel = colors.get("selection_color", "#005A9E")
        accent_text = colors.get("accent_text_color") or colors.get("selection_text_color") or _contrast_text_color(sel, fg)

        for menu in getattr(self, "menu_widgets", []):
            apply_menu_theme(menu, bg, fg, sel, accent_text)

        try:
            self.ruler.configure(bg=bg, fg=fg, insertbackground=fg, highlightthickness=0)
        except Exception:
            pass

        try:
            self.edit_box.configure(bg=bg, fg=fg, insertbackground=fg, selectbackground=sel, selectforeground=accent_text)
        except Exception:
            pass
    # --------------------------------------------------------
    # Scroll sync
    # --------------------------------------------------------
    def _scroll_both(self, *args):
        self.tree.yview(*args)
        self.value_tree.yview(*args)

    def _on_mouse_wheel(self, event):
        """Scroll both tree panes together when the mouse wheel is used."""
        if hasattr(event, "delta") and event.delta:
            steps = max(1, int(abs(event.delta) / 120))
            direction = -1 if event.delta > 0 else 1
            self.tree.yview_scroll(direction * steps, "units")
            self.value_tree.yview_scroll(direction * steps, "units")
            return "break"

        if event.num == 4:
            direction = -1
        elif event.num == 5:
            direction = 1
        else:
            return

        self.tree.yview_scroll(direction, "units")
        self.value_tree.yview_scroll(direction, "units")
        return "break"
    # --------------------------------------------------------
    # OPEN LAYOUT
    # --------------------------------------------------------
    def open_binary_lab(self):
        if self.binary_lab_window is not None:
            try:
                if self.binary_lab_window.winfo_exists():
                    self.binary_lab_window.deiconify()
                    self.binary_lab_window.lift()
                    self.binary_lab_window.focus_set()
                    return
            except tk.TclError:
                pass

        self.binary_lab_window = BinaryLabWindow(
            self.root,
            DATA_DIR,
            LAYOUT_DIR,
            APP_DIRECTORY,
            load_layout_file,
        )

    def _load_layout_path(self, path, reset_record=False):
        path = os.path.realpath(os.path.abspath(path))
        self.layout = load_layout_file(path)
        self.current_layout_path = path
        self.layout_name_var.set(f"Layout: {os.path.basename(path)}")
        self.tree.delete(*self.tree.get_children())
        self.value_tree.delete(*self.value_tree.get_children())

        for field in self.layout:
            tags = ("group",) if field["pic"].upper() == "GROUP" else ()
            self.tree.insert(
                "",
                "end",
                values=(field["level"], field["name"], field["pic"], field["start"], field["end"]),
                tags=tags,
            )
            self.value_tree.insert("", "end", values=("",))

        self.record_length = self.layout[-1]["end"] if self.layout else 0
        if reset_record:
            self.current_record = 0
        if self.key_mode:
            self.total_records = len(self.records)
        elif self.data and self.record_length > 0:
            self.total_records = len(self.data) // self.record_length
        else:
            self.total_records = 0

        self.update_ruler()
        self.update_record_count()
        self.refresh_values()
        self.clear_edit_box()

    def _apply_key_layout_for_current_record(self):
        config = load_key_definition()
        self.key_mode = config.get("mode") == "key" and bool(self.records)
        if not self.key_mode or not 0 <= self.current_record < len(self.records):
            return False

        layout_path = select_layout_for_record(self.records[self.current_record], config)
        if not layout_path:
            self.status_label.config(text="No layout matches this record key; keeping the current layout.")
            return False

        filename = _layout_filename(layout_path)
        if not filename:
            self.status_label.config(
                text=f"The mapped layout must be inside {os.path.basename(LAYOUT_DIR)}."
            )
            return False

        full_path = os.path.realpath(os.path.join(LAYOUT_DIR, filename))
        if not os.path.isfile(full_path):
            self.status_label.config(text=f"Mapped layout not found: {filename}")
            return False
        if full_path == self.current_layout_path:
            return True

        try:
            self._load_layout_path(full_path)
        except (OSError, ValueError) as error:
            self.status_label.config(text=f"Could not load mapped layout: {error}")
            return False
        return True

    def open_layout(self):
        path = filedialog.askopenfilename(
            title="Select .fad Layout File",
            initialdir=LAYOUT_DIR if os.path.isdir(LAYOUT_DIR) else APP_DIRECTORY,
            filetypes=[("FAD Files", "*.fad")]
        )
        if not path:
            return

        self._load_layout_path(path, reset_record=True)
        self._apply_key_layout_for_current_record()
    # --------------------------------------------------------
    # OPEN DATA FILE
    # --------------------------------------------------------
    def open_data(self):
        path = filedialog.askopenfilename(
            title="Select Data File",
            initialdir=DATA_DIR if os.path.isdir(DATA_DIR) else APP_DIRECTORY,
            filetypes=[("All Files", "*.*")]
        )
        if not path:
            return

        self.data_file_path = path
        self.key_mode = load_key_definition().get("mode") == "key"
        self.records = load_data_records(path) if self.key_mode else []
        self.data = bytearray(b"".join(self.records)) if self.key_mode else load_data_file(path)

        self.filename_label.config(text=f"Data File: {path}")

        if self.key_mode:
            self.total_records = len(self.records)
        elif self.record_length > 0:
            self.total_records = len(self.data) // self.record_length
        else:
            self.total_records = 0

        self.current_record = 0
        self.record_entry.delete(0, tk.END)
        self.record_entry.insert(0, "1")
        self._apply_key_layout_for_current_record()
        self.update_record_count()
        self.refresh_values()
        self.clear_edit_box()
    # --------------------------------------------------------
    # NEW DATA FILE
    # --------------------------------------------------------
    def new_data_file(self):
        self.data = bytearray()
        self.records = []
        self.key_mode = False
        self.data_file_path = None

        self.current_record = 0
        self.total_records = 0

        self.value_tree.delete(*self.value_tree.get_children())
        self.tree.selection_remove(self.tree.selection())
        self.clear_edit_box()

        self.record_entry.delete(0, tk.END)
        self.record_entry.insert(0, "1")
        self.update_record_count()

        self.filename_label.config(text="New data file (unsaved)")
        self.layout_name_var.set("Layout: (none)")
        self.update_ruler()
    # --------------------------------------------------------
    # SAVE DATA FILE
    # --------------------------------------------------------
    def save_data_file(self):
        if not self.data_file_path:
            return

        if self.key_mode:
            with open(self.data_file_path, "wb") as data_file:
                data_file.write(b"\r\n".join(self.records))
            return

        if self.record_length <= 0:
            return

        total = len(self.data) // self.record_length
        output = []

        for rec in range(total):
            start = rec * self.record_length
            end = start + self.record_length
            output.append(self.data[start:end])

        # Insert CRLF between records
        final_bytes = b"\r\n".join(output)

        with open(self.data_file_path, "wb") as f:
            f.write(final_bytes)
    # --------------------------------------------------------
    # SAVE DATA FILE AS
    # --------------------------------------------------------
    def save_data_file_as(self):
        path = filedialog.asksaveasfilename(
            title="Save Data File As",
            defaultextension="",
            filetypes=[("All Files", "*.*")]
        )
        if not path:
            return

        if self.key_mode:
            with open(path, "wb") as data_file:
                data_file.write(b"\r\n".join(self.records))
            self.data_file_path = path
            self.filename_label.config(text=f"Data File: {path}")
            return

        if self.record_length <= 0:
            return

        total = len(self.data) // self.record_length
        output = []

        for rec in range(total):
            start = rec * self.record_length
            end = start + self.record_length
            output.append(self.data[start:end])

        final_bytes = b"\r\n".join(output)

        with open(path, "wb") as f:
            f.write(final_bytes)

        self.data_file_path = path
        self.filename_label.config(text=f"Data File: {path}")
    # --------------------------------------------------------
    # PREV/NEXT RECORD
    # --------------------------------------------------------
    def prev_record(self):
        if self.current_record > 0:
            self.current_record -= 1
            self.record_entry.delete(0, tk.END)
            self.record_entry.insert(0, str(self.current_record + 1))
            self._apply_key_layout_for_current_record()
            self.update_record_count()
            self.refresh_values()
            self.clear_edit_box()
    def next_record(self):
        if self.current_record + 1 < self.total_records:
            self.current_record += 1
            self.record_entry.delete(0, tk.END)
            self.record_entry.insert(0, str(self.current_record + 1))
            self._apply_key_layout_for_current_record()
            self.update_record_count()
            self.refresh_values()
            self.clear_edit_box()
    # --------------------------------------------------------
    # JUMP TO RECORD
    # --------------------------------------------------------
    def jump_to_record(self):
        if self.total_records == 0 or (not self.key_mode and self.record_length == 0):
            return

        try:
            rec = int(self.jump_entry.get()) - 1
        except ValueError:
            return

        if rec < 0:
            rec = 0
        if rec >= self.total_records:
            rec = self.total_records - 1

        self.current_record = rec

        self.record_entry.delete(0, tk.END)
        self.record_entry.insert(0, str(self.current_record + 1))

        self._apply_key_layout_for_current_record()
        self.update_record_count()
        self.refresh_values()
        self.clear_edit_box()
    # --------------------------------------------------------
    # INSERT RECORD (after current)
    # --------------------------------------------------------
    def insert_record(self):
        if self.key_mode:
            if not self.records:
                return
            new_record = bytearray(b" " * len(self.records[self.current_record]))
            insert_index = self.current_record + 1
            self.records.insert(insert_index, new_record)
            self.data = bytearray(b"".join(self.records))
            self.current_record = insert_index
            self.total_records = len(self.records)
            self.record_entry.delete(0, tk.END)
            self.record_entry.insert(0, str(self.current_record + 1))
            self._apply_key_layout_for_current_record()
            self.update_record_count()
            self.refresh_values()
            self.clear_edit_box()
            return

        if self.record_length <= 0:
            return

        new_record = b" " * self.record_length

        insert_pos = (self.current_record + 1) * self.record_length
        self.data[insert_pos:insert_pos] = new_record

        self.total_records = len(self.data) // self.record_length

        self.current_record += 1

        self.record_entry.delete(0, tk.END)
        self.record_entry.insert(0, str(self.current_record + 1))

        self.update_record_count()
        self.refresh_values()
        self.clear_edit_box()
    # --------------------------------------------------------
    # DELETE RECORD
    # --------------------------------------------------------
    def delete_record(self):
        if self.key_mode:
            if not self.records:
                return
            del self.records[self.current_record]
            self.data = bytearray(b"".join(self.records))
            self.total_records = len(self.records)
            self.current_record = min(self.current_record, max(0, self.total_records - 1))
            self.record_entry.delete(0, tk.END)
            self.record_entry.insert(0, str(self.current_record + 1))
            if self.records:
                self._apply_key_layout_for_current_record()
            self.update_record_count()
            self.refresh_values()
            self.clear_edit_box()
            return

        if self.record_length <= 0 or self.total_records == 0:
            return

        start = self.current_record * self.record_length
        end   = start + self.record_length

        del self.data[start:end]

        self.total_records = len(self.data) // self.record_length

        if self.current_record >= self.total_records:
            self.current_record = max(0, self.total_records - 1)

        self.record_entry.delete(0, tk.END)
        self.record_entry.insert(0, str(self.current_record + 1))

        self.update_record_count()
        self.refresh_values()
        self.clear_edit_box()
    # --------------------------------------------------------
    # UPDATE RECORD COUNT
    # --------------------------------------------------------
    def update_record_count(self):
        self.record_label.config(
            text=f"Record {self.current_record + 1} of {self.total_records}"
        )
    # --------------------------------------------------------
    # REFRESH VALUES
    # --------------------------------------------------------
    def refresh_values(self):
        self.value_tree.delete(*self.value_tree.get_children())
        if self.key_mode and 0 <= self.current_record < len(self.records):
            record = self.records[self.current_record]
            for field in self.layout:
                val = extract_field_value(record, len(record), 0, field)
                self.value_tree.insert("", "end", values=(val,))
            return

        for field in self.layout:
            val = extract_field_value(self.data, self.record_length, self.current_record, field)
            self.value_tree.insert("", "end", values=(val,))
    # --------------------------------------------------------
    # FIELD SELECT
    # --------------------------------------------------------
    def on_field_select(self, event):
        widget = event.widget
        if widget == self.value_tree:
            sel = self.value_tree.selection()
            if not sel:
                return
            index = self.value_tree.index(sel[0])
        else:
            sel = self.tree.selection()
            if not sel:
                return
            index = self.tree.index(sel[0])

        if index >= len(self.layout):
            return

        if widget == self.tree:
            right_sel = self.value_tree.selection()
            if not right_sel or self.value_tree.index(right_sel[0]) != index:
                self.value_tree.selection_set(self.value_tree.get_children()[index])
        else:
            left_sel = self.tree.selection()
            if not left_sel or self.tree.index(left_sel[0]) != index:
                self.tree.selection_set(self.tree.get_children()[index])

        field = self.layout[index]
        if self.key_mode and 0 <= self.current_record < len(self.records):
            record = self.records[self.current_record]
            val = extract_field_value(record, len(record), 0, field)
        else:
            val = extract_field_value(self.data, self.record_length, self.current_record, field)

        self.edit_box.delete("1.0", tk.END)
        self.edit_box.insert("1.0", val)
    # --------------------------------------------------------
    # APPLY EDIT
    # --------------------------------------------------------
    def apply_edit(self):
        sel = self.tree.selection()
        if not sel:
            return

        index = self.tree.index(sel[0])
        if index >= len(self.layout):
            return

        field = self.layout[index]
        new_text = self.edit_box.get("1.0", tk.END).rstrip("\n")

        start = field["start"] - 1
        end   = field["end"]
        length = end - start

        encoded = new_text.encode("utf-8", errors="replace")

        if len(encoded) < length:
            encoded = encoded + b" " * (length - len(encoded))
        else:
            encoded = encoded[:length]

        if self.key_mode:
            record = self.records[self.current_record]
            if start < 0 or start + length > len(record):
                return
            record[start:start + length] = encoded
            self.data = bytearray(b"".join(self.records))
        else:
            offset = self.current_record * self.record_length + start
            if offset < 0 or offset + length > len(self.data):
                return
            self.data[offset:offset + length] = encoded
        self.refresh_values()
    # --------------------------------------------------------
    # CLEAR EDIT BOX
    # --------------------------------------------------------
    def clear_edit_box(self):
        self.edit_box.delete("1.0", tk.END)
    # --------------------------------------------------------
    # UPDATE RULER
    # --------------------------------------------------------
    def update_ruler(self):
        if self.record_length <= 0:
            return

        width = min(self.record_length, 200)

        ruler = ""
        pos = 1

        while len(ruler) < width:
            if pos % 10 == 0:
                ruler += str(pos // 10)
            elif pos % 5 == 0:
                ruler += "+"
            else:
                ruler += "."
            pos += 1

        self.ruler.config(state="normal")
        self.ruler.delete("1.0", tk.END)
        self.ruler.insert("1.0", ruler)
        self.ruler.config(state="disabled")
    def get_custom_colors(self, initial_colors=None):
        """
        Part 5: Full color picker dialog.
        Returns a complete theme color dictionary.
        """
        return pick_theme_colors(initial_colors)
# ------------------------------------------------------------
# RUN
# ------------------------------------------------------------
if __name__ == "__main__":
    root = tk.Tk()
    app = FileAidViewer(root)
    root.mainloop()
