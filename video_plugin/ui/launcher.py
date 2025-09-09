from __future__ import annotations

"""Plugin-owned workflow launcher for the Video plugin.

Provides multi-file and folder selection, batching, and folder-to-DITA
hierarchy mapping with a polished yet compact Tkinter UX. The launcher
delegates actual conversion per file to the registered DocumentHandler.
"""

import threading
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import re

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from lxml import etree as ET  # type: ignore

from orlando_toolkit.core.models import DitaContext


class VideoWorkflowLauncher:
    def __init__(self, plugin: Any) -> None:
        self._plugin = plugin

    # Optional interface metadata
    def get_display_name(self) -> str:
        return "Video Library Workflow"

    # Entry point called by host app
    def launch(self, app_context: Any, app_ui: Any) -> None:
        root = getattr(app_ui, 'root', None)
        if root is None:
            return

        # Modal chooser with centered positioning
        top = tk.Toplevel(root)
        top.title("Video Library Workflow")
        top.transient(root)
        top.grab_set()
        top.resizable(False, False)
        
        # Set window icon if available
        try:
            top.iconname("🎬")
        except Exception:
            pass

        frm = ttk.Frame(top, padding=20)
        frm.pack(fill="both", expand=True)

        # Header with icon
        header = ttk.Frame(frm)
        header.pack(fill="x", pady=(0, 12))
        
        ttk.Label(header, text="🎬", font=("Segoe UI", 16)).pack(side="left", padx=(0, 8))
        ttk.Label(header, text="Create a DITA project from:", font=("Segoe UI", 11, "bold")).pack(side="left")

        # Action buttons 
        btns = ttk.Frame(frm)
        btns.pack(fill="x", pady=(8, 12))
        btns.columnconfigure(0, weight=1)
        btns.columnconfigure(1, weight=1)

        def choose_files():
            top.destroy()
            self._start_files_flow(app_context, app_ui)

        def choose_folder():
            top.destroy()
            self._start_folder_flow(app_context, app_ui)

        btn_files = ttk.Button(btns, text="📁 Select Files…", command=choose_files)
        btn_files.grid(row=0, column=0, sticky="ew", padx=(0, 6), ipady=4)
        
        btn_folder = ttk.Button(btns, text="📂 Select Folder…", command=choose_folder)
        btn_folder.grid(row=0, column=1, sticky="ew", padx=(6, 0), ipady=4)


        tip_frame = ttk.Frame(frm)
        tip_frame.pack(fill="x", pady=(8, 0))
        
        ttk.Label(tip_frame, text="💡", font=("Segoe UI", 10)).pack(side="left", padx=(0, 6))
        ttk.Label(tip_frame, text="Folder selection preserves hierarchy as DITA sections",
                  foreground="#666", font=("Segoe UI", 9)).pack(side="left")

        # Center window on parent
        top.update_idletasks()  # Ensure window size is calculated
        width = top.winfo_reqwidth()
        height = top.winfo_reqheight()
        
        # Get parent window position and size
        parent_x = root.winfo_rootx()
        parent_y = root.winfo_rooty()
        parent_width = root.winfo_width()
        parent_height = root.winfo_height()
        
        # Calculate center position
        x = parent_x + (parent_width // 2) - (width // 2)
        y = parent_y + (parent_height // 2) - (height // 2)
        
        # Ensure window stays on screen
        x = max(0, min(x, root.winfo_screenwidth() - width))
        y = max(0, min(y, root.winfo_screenheight() - height))
        
        top.geometry(f"{width}x{height}+{x}+{y}")
        
        # Keyboard shortcuts and focus
        top.bind("<Escape>", lambda e: top.destroy())
        top.bind("<Return>", lambda e: choose_files())  # Enter = Files (most common)
        top.bind("<F>", lambda e: choose_files())
        top.bind("<D>", lambda e: choose_folder())  # D for Directory
        
        # Set focus to first button
        btn_files.focus_set()

    # ---------- Files flow ----------
    def _start_files_flow(self, app_context: Any, app_ui: Any) -> None:
        try:
            formats = self._get_supported_extensions_for_plugin(app_context, self._plugin.plugin_id)
            if formats:
                pattern = " ".join(f"*{ext}" for ext in formats)
                filetypes = [("Supported Videos", pattern), ("All files", "*.*")]
            else:
                filetypes = [("All files", "*.*")]
        except Exception:
            filetypes = [("All files", "*.*")]

        paths = filedialog.askopenfilenames(
            title="Select video files",
            filetypes=filetypes
        )
        if not paths:
            return
        files = [Path(p) for p in paths]
        self._run_batch_conversion(app_context, app_ui, files, root_folder=None)

    # ---------- Folder flow ----------
    def _start_folder_flow(self, app_context: Any, app_ui: Any) -> None:
        folder = filedialog.askdirectory(title="Select videos folder")
        if not folder:
            return
        root = Path(folder)
        exts = set(self._get_supported_extensions_for_plugin(app_context, self._plugin.plugin_id))
        files: List[Path] = []
        for dirpath, _dirnames, filenames in os.walk(root):
            for name in filenames:
                p = Path(dirpath) / name
                if p.suffix.lower() in exts:
                    files.append(p)
        if not files:
            messagebox.showinfo("No videos found", "No supported video files were found in the selected folder.")
            return
        self._run_batch_conversion(app_context, app_ui, files, root_folder=root)

    # ---------- Batch conversion ----------
    def _run_batch_conversion(self, app_context: Any, app_ui: Any,
                              files: List[Path], root_folder: Optional[Path]) -> None:
        # Progress UI
        try:
            if getattr(app_ui, 'status_label', None):
                app_ui.status_label.config(text="")
            app_ui._show_loading_spinner("Converting Videos", "")
            app_ui._disable_all_ui_elements()
        except Exception:
            pass

        # Threaded conversion to keep UI responsive
        def work():
            try:
                ctx = self._convert_many(app_context, files, root_folder)
                # Hand off to the host app on the UI thread
                app_ui.root.after(0, app_ui.on_conversion_success, ctx)
            except Exception as e:
                def _fail():
                    try:
                        app_ui._hide_loading_spinner()
                        app_ui._enable_all_ui_elements()
                    except Exception:
                        pass
                    messagebox.showerror("Conversion Error", str(e))
                app_ui.root.after(0, _fail)

        threading.Thread(target=work, daemon=True).start()

    # ---------- Core helpers ----------
    def _get_supported_extensions_for_plugin(self, app_context: Any, plugin_id: str) -> List[str]:
        try:
            formats = app_context.plugin_manager.get_plugin_metadata(plugin_id).supported_formats or []
            exts = [f.get('extension') for f in formats if isinstance(f, dict) and f.get('extension')]
            # Fallback to handler if needed
            if not exts and hasattr(app_context.service_registry, 'get_document_handlers'):
                for h in app_context.service_registry.get_document_handlers():
                    pid = app_context.service_registry.get_plugin_for_handler(h)
                    if pid == plugin_id:
                        try:
                            exts.extend(h.get_supported_extensions())
                        except Exception:
                            pass
            return sorted({e.lower() for e in exts if e})
        except Exception:
            return []

    def _convert_many(self, app_context: Any, files: List[Path], root_folder: Optional[Path]) -> DitaContext:
        # Build a fresh combined context
        combined = DitaContext()
        # Prefill UI fields: Manual Title and Revision Date
        combined.metadata["manual_title"] = "VIDEO-LIBRARY"
        try:
            combined.metadata["revision_date"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        except Exception:
            combined.metadata["revision_date"] = datetime.utcnow().strftime("%Y-%m-%d")
        try:
            if not combined.plugin_data:
                combined.plugin_data = {}
        except Exception:
            pass
        combined.plugin_data['_source_plugin'] = getattr(self._plugin, 'plugin_id', 'orlando-video-plugin')
        # Prefer an explicit language for map consistency (harmless if SaaS ignores it)
        try:
            if combined.ditamap_root is not None:
                combined.ditamap_root.set('xml:lang', 'en-US')
        except Exception:
            pass
        # Provide SaaS-friendly DOCTYPE hints (core respects these generically)
        combined.metadata['doctype_map'] = '<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "./dtd/technicalContent/dtd/map.dtd">'
        combined.metadata['doctype_concept'] = '<!DOCTYPE concept PUBLIC "-//OASIS//DTD DITA 1.3 Concept//EN" "../dtd/technicalContent/dtd/concept.dtd">'

        # Create a root ditamap (core save enforces title/metadata globally)
        map_el = ET.Element("map")
        try:
            map_el.set('xml:lang', 'en-US')
        except Exception:
            pass
        combined.ditamap_root = map_el

        # Ensure map-level topicmeta with manual_reference and temporal metadata
        def _norm_manual_ref(title: str) -> str:
            t = (title or "VIDEO-LIBRARY").strip()
            t = re.sub(r"[^A-Za-z0-9]+", "-", t)
            t = re.sub(r"-{2,}", "-", t).strip("-")
            return t.upper() or "VIDEO-LIBRARY"
        # Map-level topicmeta (manual_reference/manualCode/critdates) now enforced in core save

        # Build a folder node cache: rel_dir (str) -> topichead element
        folder_nodes: Dict[str, ET.Element] = {}

        # Decide handler lookup strategy: reuse first compatible handler
        service_registry = app_context.service_registry

        # Track collisions
        def _dedup_name(name: str, used: Dict[str, Any]) -> str:
            if name not in used:
                return name
            base, ext = os.path.splitext(name)
            i = 2
            new = f"{base}-{i}{ext}"
            while new in used:
                i += 1
                new = f"{base}-{i}{ext}"
            return new

        for f in files:
            handler = service_registry.find_handler_for_file(f)
            if handler is None:
                # Skip unsupported file silently to keep flow resilient
                continue
            # Minimal metadata; host’s prepare_package will finalize naming
            md = {
                "manual_title": combined.metadata.get("manual_title", "Videos"),
            }
            ctx = handler.convert_to_dita(f, md)

            # Merge topics
            rename_map: Dict[str, str] = {}
            for tname, topic_el in ctx.topics.items():
                safe_name = _dedup_name(tname, combined.topics)
                combined.topics[safe_name] = topic_el
                if safe_name != tname:
                    rename_map[tname] = safe_name

            # Merge media (images/videos) if any
            for iname, blob in ctx.images.items():
                s = _dedup_name(iname, combined.images)
                combined.images[s] = blob
            for vname, blob in ctx.videos.items():
                s = _dedup_name(vname, combined.videos)
                combined.videos[s] = blob

            # Merge per-video metadata for panel tooltips
            try:
                src_map = ((ctx.plugin_data or {}).get('orlando-video-plugin', {}).get('video_info_map', {}))
                if src_map:
                    dst = combined.plugin_data.setdefault('orlando-video-plugin', {}).setdefault('video_info_map', {})
                    for k, v in src_map.items():
                        key = _dedup_name(k, dst)
                        dst[key] = v
            except Exception:
                pass

            # Determine the topic filename referenced by the child map
            # The child context typically has a single root topicref -> topics/<filename>
            href = None
            child_map = ctx.ditamap_root
            if child_map is not None:
                tref = child_map.find('.//topicref[@href]')
                if tref is not None:
                    href = tref.get('href')
            # Fallback: best-effort pick first topic filename
            if not href and ctx.topics:
                href = f"topics/{next(iter(ctx.topics.keys()))}"

            # Place topicref under proper folder head
            if href:
                parent = map_el
                if root_folder is not None:
                    rel = f.relative_to(root_folder).parent
                    rel_key = str(rel).replace(os.sep, '/') if str(rel) != '.' else ''
                    if rel_key:
                        parent = self._ensure_folder_nodes(map_el, folder_nodes, rel_key)
                # Append topicref
                tref = ET.SubElement(parent, "topicref")
                # Adjust href if the topic filename was de-duplicated
                try:
                    base = os.path.basename(href)
                    new_base = rename_map.get(base, base)
                    tref.set("href", f"topics/{new_base}")
                    # Provide navtitle so the UI shows the video name, not a generic label
                    topicmeta = ET.SubElement(tref, "topicmeta")
                    nav = ET.SubElement(topicmeta, "navtitle")
                    nav.text = f.stem
                except Exception:
                    tref.set("href", href)

        return combined

    def _ensure_folder_nodes(self, map_el: ET.Element, cache: Dict[str, ET.Element], rel_key: str) -> ET.Element:
        """Ensure nested topichead nodes exist for the given rel path (a/b/c)."""
        if rel_key in cache:
            return cache[rel_key]
        parts = [p for p in rel_key.split('/') if p]
        path_accum = []
        parent = map_el
        for part in parts:
            path_accum.append(part)
            key = "/".join(path_accum)
            if key in cache:
                parent = cache[key]
                continue
            head = ET.SubElement(parent, "topichead")
            meta = ET.SubElement(head, "topicmeta")
            nav = ET.SubElement(meta, "navtitle")
            nav.text = part
            cache[key] = head
            parent = head
        return parent
