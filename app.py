"""
app.py — MainApp: window layout, shared state, and event wiring.
"""

from __future__ import annotations

import threading
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Optional
import tkinter as tk
import tkinter.ttk as ttk

import pydicom

import dicom_io
from dicom_io import AnonRule
from panels import AnonymiseDialog, FileListPanel, ImageViewerPanel, TagTreePanel


class MainApp:
    """
    Top-level application.

    Shared state:
      _all_paths     — all discovered DICOM file paths
      _current_ds    — currently displayed FileDataset
      _current_path  — path of the currently displayed file
      _anom_rules    — active anonymisation profile (persists between file switches)
    """

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self._all_paths: list[Path] = []
        self._current_ds: Optional[pydicom.dataset.FileDataset] = None
        self._current_path: Optional[Path] = None
        self._anom_rules: dict[int, AnonRule] = {}
        self._status_var = tk.StringVar(value="Ready — open a folder to begin")

        self._build_menu()
        self._build_toolbar()
        self._build_panels()
        self._build_statusbar()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)

        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(
            label="Open Folder…", accelerator="Ctrl+O", command=self.on_open_folder
        )
        file_menu.add_separator()
        file_menu.add_command(
            label="Save Current As…", accelerator="Ctrl+S", command=self.on_save_current
        )
        file_menu.add_command(
            label="Save All Anonymised…",
            accelerator="Ctrl+Shift+S",
            command=self.on_save_all,
        )
        file_menu.add_separator()
        file_menu.add_command(
            label="Quit", accelerator="Ctrl+Q", command=self.root.quit
        )
        menubar.add_cascade(label="File", menu=file_menu)

        anon_menu = tk.Menu(menubar, tearoff=False)
        anon_menu.add_command(
            label="Configure Rules…", command=self.on_anonymise_selected
        )
        anon_menu.add_separator()
        anon_menu.add_command(label="Select All Tags", command=self._select_all_tags)
        anon_menu.add_command(label="Clear Selection", command=self._clear_selection)
        menubar.add_cascade(label="Anonymise", menu=anon_menu)

        profile_menu = tk.Menu(menubar, tearoff=False)
        profile_menu.add_command(
            label="Load Profile…", accelerator="Ctrl+Shift+L", command=self.on_load_profile
        )
        profile_menu.add_command(
            label="Save Profile…", accelerator="Ctrl+Shift+P", command=self.on_save_profile
        )
        menubar.add_cascade(label="Profile", menu=profile_menu)

        self.root.config(menu=menubar)

        # Keyboard shortcuts
        self.root.bind("<Control-o>", lambda _e: self.on_open_folder())
        self.root.bind("<Control-s>", lambda _e: self.on_save_current())
        self.root.bind("<Control-S>", lambda _e: self.on_save_all())
        self.root.bind("<Control-L>", lambda _e: self.on_load_profile())
        self.root.bind("<Control-P>", lambda _e: self.on_save_profile())
        self.root.bind("<Control-q>", lambda _e: self.root.quit())

    def _build_toolbar(self) -> None:
        toolbar = ttk.Frame(self.root, relief="flat")
        toolbar.pack(side=tk.TOP, fill=tk.X, padx=4, pady=(4, 0))

        ttk.Button(toolbar, text="Open Folder", command=self.on_open_folder).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(
            toolbar, text="Anonymise Selected", command=self.on_anonymise_selected
        ).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Save Current", command=self.on_save_current).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(toolbar, text="Save All", command=self.on_save_all).pack(
            side=tk.LEFT, padx=2
        )

        ttk.Label(toolbar, textvariable=self._status_var, font=("", 9)).pack(
            side=tk.RIGHT, padx=8
        )

    def _build_panels(self) -> None:
        paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=4, pady=4)

        self.file_panel = FileListPanel(paned, on_select=self.on_file_selected)
        self.image_panel = ImageViewerPanel(paned)
        self.tag_panel = TagTreePanel(paned)

        paned.add(self.file_panel, weight=0)
        paned.add(self.image_panel, weight=2)
        paned.add(self.tag_panel, weight=1)

        # Set initial sash positions after window is drawn
        self.root.update_idletasks()
        try:
            paned.sashpos(0, 220)
            paned.sashpos(1, 780)
        except Exception:
            pass

    def _build_statusbar(self) -> None:
        status_bar = ttk.Frame(self.root, relief="sunken")
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        ttk.Label(status_bar, textvariable=self._status_var, font=("Courier", 9)).pack(
            side=tk.LEFT, padx=6, pady=2
        )

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def on_open_folder(self) -> None:
        folder = filedialog.askdirectory(title="Select DICOM Folder")
        if not folder:
            return
        self._status_var.set("Discovering DICOM files…")
        self.root.update_idletasks()
        thread = threading.Thread(
            target=self._discover_worker,
            args=(folder,),
            daemon=True,
        )
        thread.start()

    def _discover_worker(self, folder: str) -> None:
        paths = dicom_io.discover_dicom_files(folder)
        self.root.after(0, self._on_files_discovered, paths)

    def _on_files_discovered(self, paths: list[Path]) -> None:
        self._all_paths = paths
        self.file_panel.set_files(paths)
        if paths:
            self._status_var.set(f"{len(paths)} file(s) found")
            self.file_panel.select_index(0)
        else:
            self._status_var.set("No DICOM files found in selected folder")

    def on_file_selected(self, path: Path) -> None:
        self._current_path = path
        self._status_var.set(f"Loading {path.name}…")
        self.root.update_idletasks()

        try:
            ds = dicom_io.load_dicom(path)
        except Exception as exc:
            self.file_panel.highlight_error(path)
            self.image_panel.clear()
            self.tag_panel.clear()
            self._status_var.set(f"Error loading {path.name}: {exc}")
            return

        self._current_ds = ds

        # Build info dict for image panel
        info = {
            "filename": path.name,
            "modality": str(getattr(ds, "Modality", "")),
            "ww": str(getattr(ds, "WindowWidth", "")),
            "wl": str(getattr(ds, "WindowCenter", "")),
            "size": (
                f"{ds.Rows}×{ds.Columns}"
                if hasattr(ds, "Rows") and hasattr(ds, "Columns")
                else ""
            ),
        }

        canvas_sz = self.image_panel.canvas_size()
        photo = dicom_io.get_display_image(ds, max_size=canvas_sz)
        self.image_panel.show_image(photo, info)

        nodes = dicom_io.build_tag_nodes(ds)
        self.tag_panel.populate(nodes)

        # Restore previously selected tags (persistent profile)
        if self._anom_rules:
            self.tag_panel.restore_checked(set(self._anom_rules.keys()))

        n_rules = len(self._anom_rules)
        rule_str = f" | {n_rules} rule(s) active" if n_rules else ""
        self._status_var.set(f"{len(self._all_paths)} file(s) | {path.name}{rule_str}")

    def on_anonymise_selected(self) -> None:
        checked = self.tag_panel.get_checked_tags()
        if not checked:
            messagebox.showinfo(
                "No Tags Selected",
                "Check one or more tags in the tree before configuring rules.",
                parent=self.root,
            )
            return

        dialog = AnonymiseDialog(self.root, checked)
        if dialog.result is None:
            return  # cancelled

        if dialog.scope == "current":
            # Apply rules to current file only — update in-memory dataset and refresh tree
            if self._current_ds is not None:
                self._current_ds = dicom_io.anonymise_dataset(
                    self._current_ds, dialog.result
                )
                nodes = dicom_io.build_tag_nodes(self._current_ds)
                self.tag_panel.populate(nodes)
                self.tag_panel.restore_checked(set(dialog.result.keys()))
            self._status_var.set(
                f"Applied {len(dialog.result)} rule(s) to {self._current_path.name if self._current_path else 'current file'}"
            )
        else:
            # "all" — store as global profile for batch save
            self._anom_rules = dialog.result
            self._status_var.set(
                f"{len(self._anom_rules)} rule(s) configured — use 'Save All' to apply"
            )

    def on_save_current(self) -> None:
        if self._current_ds is None:
            messagebox.showwarning(
                "No File Open", "Open a DICOM file first.", parent=self.root
            )
            return

        default_name = (
            self._current_path.name if self._current_path else "anonymised.dcm"
        )
        output_path = filedialog.asksaveasfilename(
            title="Save Anonymised DICOM",
            initialfile=default_name,
            defaultextension=".dcm",
            filetypes=[("DICOM files", "*.dcm"), ("All files", "*.*")],
            parent=self.root,
        )
        if not output_path:
            return

        try:
            anon_ds = dicom_io.anonymise_dataset(self._current_ds, self._anom_rules)
            dicom_io.save_dicom(anon_ds, Path(output_path))
            self._status_var.set(f"Saved: {Path(output_path).name}")
        except Exception as exc:
            messagebox.showerror("Save Error", str(exc), parent=self.root)

    def on_save_all(self) -> None:
        if not self._all_paths:
            messagebox.showwarning(
                "No Files",
                "Open a folder containing DICOM files first.",
                parent=self.root,
            )
            return

        if not self._anom_rules:
            messagebox.showwarning(
                "No Rules Configured",
                "Select tags and configure anonymisation rules first\n"
                "(use 'Anonymise Selected' → 'Apply to All Files').",
                parent=self.root,
            )
            return

        output_folder = filedialog.askdirectory(title="Select Output Folder")
        if not output_folder:
            return

        self._run_batch_save(Path(output_folder))

    def on_load_profile(self) -> None:
        """Load an anonymisation profile from a YAML file."""
        path = filedialog.askopenfilename(
            title="Load Anonymisation Profile",
            filetypes=[("YAML files", "*.yaml *.yml"), ("All files", "*.*")],
            parent=self.root,
        )
        if not path:
            return
        try:
            rules = dicom_io.load_profile(Path(path))
        except Exception as exc:
            messagebox.showerror("Load Profile Error", str(exc), parent=self.root)
            return

        self._anom_rules = rules
        # Restore checkmarks in the tag tree for any matching tag
        if self._current_ds is not None:
            self.tag_panel.restore_checked(set(rules.keys()))
        self._status_var.set(
            f"Profile loaded: {len(rules)} rule(s) from {Path(path).name}"
        )

    def on_save_profile(self) -> None:
        """Save the current anonymisation rules as a YAML profile."""
        if not self._anom_rules:
            messagebox.showwarning(
                "No Rules",
                "Configure anonymisation rules first before saving a profile.",
                parent=self.root,
            )
            return

        path = filedialog.asksaveasfilename(
            title="Save Anonymisation Profile",
            defaultextension=".yaml",
            filetypes=[("YAML files", "*.yaml"), ("All files", "*.*")],
            parent=self.root,
        )
        if not path:
            return
        try:
            dicom_io.save_profile(self._anom_rules, Path(path))
            self._status_var.set(f"Profile saved: {Path(path).name}")
        except Exception as exc:
            messagebox.showerror("Save Profile Error", str(exc), parent=self.root)

    def _run_batch_save(self, output_folder: Path) -> None:
        total = len(self._all_paths)
        progress_win = tk.Toplevel(self.root)
        progress_win.title("Saving…")
        progress_win.resizable(False, False)
        progress_win.transient(self.root)
        progress_win.grab_set()

        ttk.Label(progress_win, text=f"Anonymising and saving {total} file(s)…").pack(
            padx=20, pady=(14, 6)
        )
        progress_var = tk.IntVar(value=0)
        progress_bar = ttk.Progressbar(
            progress_win, variable=progress_var, maximum=total, length=340
        )
        progress_bar.pack(padx=20, pady=(0, 6))
        progress_label = ttk.Label(progress_win, text="0 / " + str(total))
        progress_label.pack(pady=(0, 14))

        errors: list[str] = []

        def _worker() -> None:
            for i, path in enumerate(self._all_paths):
                try:
                    ds = dicom_io.load_dicom(path)
                    anon_ds = dicom_io.anonymise_dataset(ds, self._anom_rules)
                    out_path = output_folder / path.name
                    dicom_io.save_dicom(anon_ds, out_path)
                except Exception as exc:
                    errors.append(f"{path.name}: {exc}")
                self.root.after(0, _update_progress, i + 1)

            self.root.after(0, _on_done)

        def _update_progress(done: int) -> None:
            progress_var.set(done)
            progress_label.config(text=f"{done} / {total}")

        def _on_done() -> None:
            progress_win.destroy()
            if errors:
                detail = "\n".join(errors[:10])
                if len(errors) > 10:
                    detail += f"\n… and {len(errors) - 10} more"
                messagebox.showwarning(
                    "Completed with errors",
                    f"{total - len(errors)} file(s) saved. {len(errors)} error(s):\n\n{detail}",
                    parent=self.root,
                )
            else:
                messagebox.showinfo(
                    "Done",
                    f"All {total} file(s) anonymised and saved to:\n{output_folder}",
                    parent=self.root,
                )
            self._status_var.set(
                f"Saved {total - len(errors)}/{total} file(s) → {output_folder}"
            )

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()

    # ------------------------------------------------------------------
    # Helper actions (menu commands)
    # ------------------------------------------------------------------

    def _select_all_tags(self) -> None:
        """Check every checkable item in the tree."""
        for iid in self.tag_panel._checked:
            if not self.tag_panel._checked[iid]:
                self.tag_panel._set_checked(iid, True)

    def _clear_selection(self) -> None:
        """Uncheck every item in the tree."""
        for iid in list(self.tag_panel._checked.keys()):
            if self.tag_panel._checked[iid]:
                self.tag_panel._set_checked(iid, False)
