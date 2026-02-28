"""
panels.py — All UI panels for the DICOM Anonymiser.

Panels:
  FileListPanel     — left: scrollable file list
  ImageViewerPanel  — centre: DICOM image on a dark canvas
  TagTreePanel      — right: DICOM header tree with checkbox selection
  AnonymiseDialog   — modal: configure per-tag anonymisation rules
"""

from __future__ import annotations

import dataclasses
import tkinter as tk
import tkinter.ttk as ttk
from tkinter import messagebox
from pathlib import Path
from typing import Callable, Optional

from PIL import ImageTk

from dicom_io import AnonAction, AnonRule, TagNode


# ---------------------------------------------------------------------------
# FileListPanel
# ---------------------------------------------------------------------------


class FileListPanel(ttk.Frame):
    """Scrollable list of discovered DICOM files (left panel)."""

    def __init__(self, master: tk.Widget, on_select: Callable[[Path], None]) -> None:
        super().__init__(master)
        self._on_select_cb = on_select
        self._paths: list[Path] = []

        self._label_var = tk.StringVar(value="DICOM Files (0)")
        lbl = ttk.Label(self, textvariable=self._label_var, font=("", 10, "bold"))
        lbl.pack(side=tk.TOP, fill=tk.X, padx=6, pady=(6, 2))

        frame = ttk.Frame(self)
        frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=4, pady=4)

        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL)
        self._listbox = tk.Listbox(
            frame,
            yscrollcommand=scrollbar.set,
            selectmode=tk.SINGLE,
            activestyle="none",
            font=("Courier", 10),
            bg="#2b2b2b",
            fg="#d4d4d4",
            selectbackground="#0066cc",
            selectforeground="white",
            borderwidth=0,
            highlightthickness=0,
        )
        scrollbar.config(command=self._listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._listbox.bind("<<ListboxSelect>>", self._on_listbox_select)

    def set_files(self, paths: list[Path]) -> None:
        self._paths = paths
        self._listbox.delete(0, tk.END)
        for p in paths:
            self._listbox.insert(tk.END, p.name)
        self._label_var.set(f"DICOM Files ({len(paths)})")

    def _on_listbox_select(self, _event: tk.Event) -> None:
        sel = self._listbox.curselection()
        if sel:
            self._on_select_cb(self._paths[sel[0]])

    def get_selected_path(self) -> Optional[Path]:
        sel = self._listbox.curselection()
        if sel:
            return self._paths[sel[0]]
        return None

    def highlight_error(self, path: Path) -> None:
        try:
            idx = self._paths.index(path)
            self._listbox.itemconfigure(idx, fg="#ff6666")
        except ValueError:
            pass

    def select_index(self, index: int) -> None:
        if 0 <= index < len(self._paths):
            self._listbox.selection_clear(0, tk.END)
            self._listbox.selection_set(index)
            self._listbox.see(index)
            self._on_select_cb(self._paths[index])


# ---------------------------------------------------------------------------
# ImageViewerPanel
# ---------------------------------------------------------------------------


class ImageViewerPanel(ttk.Frame):
    """DICOM image viewer on a dark canvas (centre panel)."""

    def __init__(self, master: tk.Widget) -> None:
        super().__init__(master)

        lbl = ttk.Label(self, text="Image Viewer", font=("", 10, "bold"))
        lbl.pack(side=tk.TOP, fill=tk.X, padx=6, pady=(6, 2))

        self._canvas = tk.Canvas(self, bg="#1a1a1a", highlightthickness=0)
        self._canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self._info_var = tk.StringVar(value="")
        info_lbl = ttk.Label(self, textvariable=self._info_var, font=("Courier", 9))
        info_lbl.pack(side=tk.BOTTOM, fill=tk.X, padx=6, pady=(2, 4))

        # Keep a reference to prevent GC
        self._photo: Optional[ImageTk.PhotoImage] = None
        self._canvas_image_id: Optional[int] = None

        self._canvas.bind("<Configure>", self._on_resize)

    def show_image(
        self,
        photo: Optional[ImageTk.PhotoImage],
        info: dict[str, str],
    ) -> None:
        self._canvas.delete("all")
        self._photo = photo

        if photo is None:
            cw = self._canvas.winfo_width() or 400
            ch = self._canvas.winfo_height() or 400
            self._canvas.create_text(
                cw // 2,
                ch // 2,
                text="No image data",
                fill="#888888",
                font=("", 14),
            )
            self._info_var.set(info.get("filename", ""))
        else:
            self._canvas_image_id = self._canvas.create_image(
                self._canvas.winfo_width() // 2 or 1,
                self._canvas.winfo_height() // 2 or 1,
                anchor=tk.CENTER,
                image=photo,
            )
            parts = []
            if info.get("modality"):
                parts.append(info["modality"])
            if info.get("ww") and info.get("wl"):
                parts.append(f"W:{info['ww']} L:{info['wl']}")
            if info.get("size"):
                parts.append(info["size"])
            if info.get("filename"):
                parts.append(info["filename"])
            self._info_var.set("  |  ".join(parts))

    def clear(self) -> None:
        self._canvas.delete("all")
        self._photo = None
        self._info_var.set("")

    def _on_resize(self, _event: tk.Event) -> None:
        if self._photo and self._canvas_image_id:
            cw = self._canvas.winfo_width()
            ch = self._canvas.winfo_height()
            self._canvas.coords(self._canvas_image_id, cw // 2, ch // 2)

    def canvas_size(self) -> tuple[int, int]:
        w = self._canvas.winfo_width()
        h = self._canvas.winfo_height()
        return (max(w, 200), max(h, 200))


# ---------------------------------------------------------------------------
# TagTreePanel
# ---------------------------------------------------------------------------


class TagTreePanel(ttk.Frame):
    """
    DICOM tag treeview with checkbox selection (right panel).

    Columns:
      #0  (tree column)  — "☐ (gggg,eeee) Keyword"
      vr                 — VR string
      value              — truncated value
    """

    def __init__(self, master: tk.Widget) -> None:
        super().__init__(master)

        lbl = ttk.Label(self, text="DICOM Tags", font=("", 10, "bold"))
        lbl.pack(side=tk.TOP, fill=tk.X, padx=6, pady=(6, 2))

        # Search bar
        search_frame = ttk.Frame(self)
        search_frame.pack(side=tk.TOP, fill=tk.X, padx=4, pady=(0, 4))
        ttk.Label(search_frame, text="Search:").pack(side=tk.LEFT, padx=(2, 4))
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", self._on_search_change)
        search_entry = ttk.Entry(search_frame, textvariable=self._search_var)
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        search_entry.bind("<Escape>", lambda _e: self._search_var.set(""))
        ttk.Button(
            search_frame, text="✕", width=2,
            command=lambda: self._search_var.set(""),
        ).pack(side=tk.LEFT, padx=(4, 0))

        tree_frame = ttk.Frame(self)
        tree_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=4, pady=4)

        ysb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL)
        xsb = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL)

        self.tree = ttk.Treeview(
            tree_frame,
            columns=("vr", "value"),
            yscrollcommand=ysb.set,
            xscrollcommand=xsb.set,
            selectmode="browse",
        )
        ysb.config(command=self.tree.yview)
        xsb.config(command=self.tree.xview)

        self.tree.heading("#0", text="Tag / Keyword", anchor=tk.W)
        self.tree.heading("vr", text="VR", anchor=tk.CENTER)
        self.tree.heading("value", text="Value", anchor=tk.W)

        self.tree.column("#0", width=360, minwidth=200, stretch=True)
        self.tree.column("vr", width=45, minwidth=40, stretch=False)
        self.tree.column("value", width=280, minwidth=100, stretch=True)

        ysb.pack(side=tk.RIGHT, fill=tk.Y)
        xsb.pack(side=tk.BOTTOM, fill=tk.X)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Tag style for sequences items (non-checkable rows)
        self.tree.tag_configure("seq_item", foreground="#999999")
        self.tree.tag_configure("leaf", foreground="#d4d4d4")
        self.tree.tag_configure("sequence", foreground="#88ccff")
        self.tree.tag_configure("checked", foreground="#66ff66")

        # Internal state
        self._all_nodes: list[TagNode] = []            # full unfiltered node list
        self._item_tag_map: dict[str, int] = {}        # item_id → int(tag)
        self._item_keyword_map: dict[str, str] = {}    # item_id → keyword
        self._checked: dict[str, bool] = {}            # item_id → checked

        self.tree.bind("<Button-1>", self._on_click)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def populate(self, nodes: list[TagNode]) -> None:
        self._all_nodes = nodes
        self._search_var.set("")   # clear search on new file
        self._rebuild_tree(nodes)

    def _rebuild_tree(self, nodes: list[TagNode]) -> None:
        """Repopulate the tree from *nodes*, restoring any previously checked tags."""
        # Save currently checked tags by int(tag) before clearing
        checked_tag_ints: set[int] = {
            tag_int
            for iid, tag_int in self._item_tag_map.items()
            if self._checked.get(iid, False)
        }
        self.tree.delete(*self.tree.get_children())
        self._item_tag_map.clear()
        self._item_keyword_map.clear()
        self._checked.clear()
        for node in nodes:
            self._insert_node(node, "")
        if checked_tag_ints:
            self.restore_checked(checked_tag_ints)

    def get_checked_tags(self) -> dict[int, str]:
        """Return {int(tag): keyword} for every checked item."""
        return {
            self._item_tag_map[iid]: self._item_keyword_map[iid]
            for iid, checked in self._checked.items()
            if checked
        }

    def restore_checked(self, tag_ints: set[int]) -> None:
        """Re-apply checked state for tags that are in *tag_ints*."""
        for iid, tag_int in self._item_tag_map.items():
            if tag_int in tag_ints and not self._checked.get(iid, False):
                self._set_checked(iid, True)

    def clear(self) -> None:
        self._all_nodes = []
        self._search_var.set("")
        self.tree.delete(*self.tree.get_children())
        self._item_tag_map.clear()
        self._item_keyword_map.clear()
        self._checked.clear()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _on_search_change(self, _name: str, _idx: str, _op: str) -> None:
        query = self._search_var.get().strip().lower()
        if query:
            filtered = self._filter_nodes(self._all_nodes, query)
        else:
            filtered = self._all_nodes
        self._rebuild_tree(filtered)
        if query:
            # Expand all items so matches are visible
            for iid in self.tree.get_children():
                self._expand_all(iid)

    def _expand_all(self, item_id: str) -> None:
        self.tree.item(item_id, open=True)
        for child in self.tree.get_children(item_id):
            self._expand_all(child)

    def _filter_nodes(self, nodes: list[TagNode], query: str) -> list[TagNode]:
        """Return a filtered copy of *nodes* where any node (or descendant) matches *query*.

        Matching is case-insensitive and checks: keyword, hex tag address, value_repr.
        """
        result: list[TagNode] = []
        for node in nodes:
            if node.keyword.startswith("Item ") and node.vr == "":
                # Synthetic "Item N" container: include only if children match
                filtered_children = self._filter_nodes(node.children, query)
                if filtered_children:
                    result.append(dataclasses.replace(node, children=filtered_children))
            elif node.vr == "SQ":
                tag_str = f"({node.tag.group:04X},{node.tag.element:04X})"
                self_matches = (
                    query in node.keyword.lower()
                    or query in tag_str.lower()
                    or query in node.value_repr.lower()
                )
                # Filter children (Item N containers)
                filtered_children = self._filter_nodes(node.children, query)
                if self_matches or filtered_children:
                    result.append(dataclasses.replace(
                        node,
                        children=filtered_children if not self_matches else node.children,
                    ))
            else:
                tag_str = f"({node.tag.group:04X},{node.tag.element:04X})"
                if (
                    query in node.keyword.lower()
                    or query in tag_str.lower()
                    or query in node.value_repr.lower()
                    or query in node.vr.lower()
                ):
                    result.append(node)
        return result

    def _insert_node(self, node: TagNode, parent_id: str) -> None:
        tag_str = f"({node.tag.group:04X},{node.tag.element:04X})"

        if node.keyword.startswith("Item ") and node.vr == "":
            # Synthetic "Item N" container — not checkable
            iid = self.tree.insert(
                parent_id,
                "end",
                text=f"  {node.keyword}",
                values=("", ""),
                tags=("seq_item",),
            )
            for child in node.children:
                self._insert_node(child, iid)
            return

        if node.vr == "SQ":
            # Real SQ tag — checkable
            iid = self.tree.insert(
                parent_id,
                "end",
                text=f"☐ {tag_str} {node.keyword}",
                values=("SQ", node.value_repr),
                tags=("sequence",),
            )
            self._item_tag_map[iid] = int(node.tag)
            self._item_keyword_map[iid] = node.keyword
            self._checked[iid] = False
            for child in node.children:
                self._insert_node(child, iid)
        else:
            # Leaf element — checkable
            iid = self.tree.insert(
                parent_id,
                "end",
                text=f"☐ {tag_str} {node.keyword}",
                values=(node.vr, node.value_repr),
                tags=("leaf",),
            )
            self._item_tag_map[iid] = int(node.tag)
            self._item_keyword_map[iid] = node.keyword
            self._checked[iid] = False

    def _on_click(self, event: tk.Event) -> None:
        col = self.tree.identify_column(event.x)
        if col != "#0":
            return
        item_id = self.tree.identify_row(event.y)
        if not item_id:
            return
        tags = self.tree.item(item_id, "tags")
        if "seq_item" in tags:
            return
        if item_id not in self._checked:
            return
        new_state = not self._checked[item_id]
        self._set_checked(item_id, new_state)

    def _set_checked(self, item_id: str, checked: bool) -> None:
        self._checked[item_id] = checked
        text = self.tree.item(item_id, "text")
        glyph = "☑" if checked else "☐"
        new_text = glyph + text[1:]
        tags = list(self.tree.item(item_id, "tags"))
        # Swap colour tag
        for old in ("checked", "leaf", "sequence"):
            if old in tags:
                tags.remove(old)
        if checked:
            tags.append("checked")
        else:
            existing_vr = self.tree.set(item_id, "vr")
            tags.append("sequence" if existing_vr == "SQ" else "leaf")
        self.tree.item(item_id, text=new_text, tags=tags)


# ---------------------------------------------------------------------------
# AnonymiseDialog
# ---------------------------------------------------------------------------


class AnonymiseDialog(tk.Toplevel):
    """
    Modal dialog to configure per-tag anonymisation rules.

    Sets:
      .result: Optional[dict[int, AnonRule]]
      .scope:  "current" | "all"  (meaningful only when result is not None)
    """

    def __init__(self, master: tk.Widget, checked_tags: dict[int, str]) -> None:
        super().__init__(master)
        self.title("Configure Anonymisation Rules")
        self.resizable(True, True)
        self.minsize(620, 300)

        self.result: Optional[dict[int, AnonRule]] = None
        self.scope: str = "current"

        self._checked_tags = checked_tags  # {int(tag): keyword}
        # row data: (tag_int, action_var, placeholder_entry)
        self._rows: list[tuple[int, tk.StringVar, tk.Entry]] = []

        self._build_ui()

        # Make modal
        self.transient(master)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.wait_window(self)

    def _build_ui(self) -> None:
        ttk.Label(
            self,
            text="Set anonymisation action for each selected tag.",
            font=("", 10),
        ).pack(padx=12, pady=(10, 4), anchor=tk.W)

        # Column headers
        hdr = ttk.Frame(self)
        hdr.pack(fill=tk.X, padx=12, pady=(0, 2))
        ttk.Label(hdr, text="Tag", width=32, font=("", 9, "bold")).grid(
            row=0, column=0, sticky=tk.W
        )
        ttk.Label(hdr, text="Action", width=14, font=("", 9, "bold")).grid(
            row=0, column=1, sticky=tk.W, padx=(4, 0)
        )
        ttk.Label(hdr, text="Placeholder value", font=("", 9, "bold")).grid(
            row=0, column=2, sticky=tk.W, padx=(4, 0)
        )
        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=12)

        # Scrollable area for tag rows
        outer = ttk.Frame(self)
        outer.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)

        canvas = tk.Canvas(outer, highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        inner = ttk.Frame(canvas)
        inner.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=inner, anchor="nw")

        # Bind mouse wheel
        def _on_mousewheel(event: tk.Event) -> None:
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind("<MouseWheel>", _on_mousewheel)

        self._build_tag_rows(inner)

        # Buttons
        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=12, pady=(4, 0))
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=12, pady=10)

        ttk.Button(
            btn_frame, text="Apply to Current File", command=self._on_apply_current
        ).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(
            btn_frame, text="Apply to All Files", command=self._on_apply_all
        ).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_frame, text="Cancel", command=self._on_cancel).pack(
            side=tk.RIGHT
        )

    def _build_tag_rows(self, container: ttk.Frame) -> None:
        actions = ["blank", "placeholder", "delete"]
        for row_idx, (tag_int, keyword) in enumerate(
            sorted(self._checked_tags.items())
        ):
            group = (tag_int >> 16) & 0xFFFF
            elem = tag_int & 0xFFFF
            tag_str = f"({group:04X},{elem:04X})"
            display = f"{keyword}  {tag_str}"[:38]

            ttk.Label(container, text=display, font=("Courier", 9), width=32).grid(
                row=row_idx, column=0, sticky=tk.W, padx=(0, 4), pady=2
            )

            action_var = tk.StringVar(value="blank")
            combo = ttk.Combobox(
                container,
                textvariable=action_var,
                values=actions,
                state="readonly",
                width=12,
            )
            combo.grid(row=row_idx, column=1, sticky=tk.W, padx=(0, 4), pady=2)

            entry = ttk.Entry(container, width=24, state="disabled")
            entry.grid(row=row_idx, column=2, sticky=tk.W, pady=2)

            # Enable entry only when "placeholder" is selected
            def _on_action_change(
                _name: str,
                _idx: str,
                _op: str,
                var: tk.StringVar = action_var,
                e: ttk.Entry = entry,
            ) -> None:
                if var.get() == "placeholder":
                    e.config(state="normal")
                else:
                    e.config(state="disabled")

            action_var.trace_add("write", _on_action_change)

            self._rows.append((tag_int, action_var, entry))

    def _collect_rules(self) -> dict[int, AnonRule]:
        rules: dict[int, AnonRule] = {}
        for tag_int, action_var, entry in self._rows:
            action_str = action_var.get()
            if action_str == "blank":
                rules[tag_int] = AnonRule(AnonAction.BLANK)
            elif action_str == "delete":
                rules[tag_int] = AnonRule(AnonAction.DELETE)
            else:  # placeholder
                rules[tag_int] = AnonRule(AnonAction.PLACEHOLDER, entry.get())
        return rules

    def _on_apply_current(self) -> None:
        self.result = self._collect_rules()
        self.scope = "current"
        self.destroy()

    def _on_apply_all(self) -> None:
        self.result = self._collect_rules()
        self.scope = "all"
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()
