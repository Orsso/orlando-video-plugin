"""Minimal Video Preview Panel (VLC PoC).

This is a clean, from-scratch panel that embeds VLC inside a ttk UI.
It focuses on the basics: list videos, play/pause, stop.
Advanced features and fallbacks are intentionally omitted.
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile
from pathlib import Path
import re
from typing import Any, Dict, List, Optional

import tkinter as tk
from tkinter import ttk
from lxml import etree as ET

logger = logging.getLogger(__name__)


class VideoPreviewPanel(ttk.Frame):
    """Minimal VLC-backed video preview panel."""
    # Icon strings via escape codes for robustness
    PLAY_ICON = "\u25B6"   # ▶
    PAUSE_ICON = "\u23F8"  # ⏸
    STOP_ICON = "\u23F9"   # ⏹

    def __init__(self, parent: tk.Widget, *, plugin_config: Dict[str, Any] = None, app_context: Optional[Any] = None, **kwargs) -> None:
        super().__init__(parent, **kwargs)
        self.plugin_config = plugin_config or {}
        self._app_context = app_context

        # State
        self._topic: Optional[ET.Element] = None
        self._context: Optional[Any] = None
        self._videos: Dict[str, bytes] = {}
        self._items: List[Dict[str, Any]] = []  # [{'display': str, 'filename': str, 'href': str}]

        # Temp files
        self._temp_dir = tempfile.mkdtemp(prefix="otk_vlc_")
        self._temp_paths: Dict[str, str] = {}

        # VLC
        self._vlc_instance = None
        self._vlc_player = None
        # Controls/polling state
        self._poll_job = None
        self._user_seeking = False
        self._updating_seek = False
        self._current_filename: Optional[str] = None
        self._last_pos_ms_by_file: Dict[str, int] = {}
        self._duration_ms: int = 0

        # UI
        self._status = tk.StringVar(value="")
        self._build_ui()
        # Try to populate immediately from AppContext when available
        self._maybe_init_from_app_context()

    # UI ---------------------------------------------------------------------
    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        header = ttk.Frame(self)
        header.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 2))
        ttk.Label(header, text="Video Preview", font=("TkDefaultFont", 9, "bold")).pack(side="left")
        ttk.Label(header, textvariable=self._status).pack(side="right")

        list_frame = ttk.Frame(self)
        list_frame.grid(row=1, column=0, sticky="ew", padx=6, pady=(0, 6))
        list_frame.columnconfigure(0, weight=1)
        self._list = tk.Listbox(list_frame, height=5, exportselection=False)
        self._list.grid(row=0, column=0, sticky="ew")
        ttk.Scrollbar(list_frame, orient="vertical", command=self._list.yview).grid(row=0, column=1, sticky="ns")
        self._list.configure(yscrollcommand=lambda *a: None)
        self._list.bind("<<ListboxSelect>>", self._on_select)

        self._surface = ttk.Frame(self)
        self._surface.grid(row=2, column=0, sticky="nsew", padx=8, pady=8)
        self._surface.columnconfigure(0, weight=1)
        self._surface.rowconfigure(0, weight=1)
        self._placeholder = ttk.Label(self._surface, text="Select a video to play", anchor="center")
        self._placeholder.grid(row=0, column=0, sticky="nsew")

        # Timeline row (full width)
        timeline = ttk.Frame(self)
        timeline.grid(row=3, column=0, sticky="ew", padx=8, pady=(0, 4))
        timeline.columnconfigure(0, weight=1)
        self._seek = ttk.Scale(timeline, from_=0, to=1000, orient='horizontal', command=self._on_seek)
        self._seek.grid(row=0, column=0, sticky='ew')
        self._seek.bind('<Button-1>', self._on_seek_click)
        self._seek.bind('<ButtonPress-1>', lambda e: self._set_user_seeking(True))
        self._seek.bind('<ButtonRelease-1>', lambda e: self._set_user_seeking(False))

        # Controls row
        controls = ttk.Frame(self)
        controls.grid(row=4, column=0, sticky="ew", padx=8, pady=(0, 8))
        controls.columnconfigure(5, weight=1)
        ttk.Button(controls, text="Prev", width=5, command=self._on_prev).grid(row=0, column=0)
        self._btn_play = ttk.Button(controls, text=self.PLAY_ICON, width=4, command=self._on_play_pause)
        self._btn_play.grid(row=0, column=1, padx=(6, 0))
        ttk.Button(controls, text=self.STOP_ICON, width=4, command=self._on_stop).grid(row=0, column=2, padx=(6, 0))
        ttk.Button(controls, text="Next", width=5, command=self._on_next).grid(row=0, column=3, padx=(6, 0))
        self._lbl_time = ttk.Label(controls, text="00:00 / 00:00")
        self._lbl_time.grid(row=0, column=4, padx=(12, 6))
        self._speed_var = tk.StringVar(value="1.0x")
        speed = ttk.Combobox(controls, textvariable=self._speed_var, values=["0.5x","1.0x","1.5x","2.0x"], width=6, state='readonly')
        speed.bind("<<ComboboxSelected>>", lambda e: self._apply_speed())
        speed.grid(row=0, column=5, padx=(8, 0))
        self._mute_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(controls, text="Mute", variable=self._mute_var, command=self._apply_mute).grid(row=0, column=6, padx=(8, 0))
        self._vol = ttk.Scale(controls, from_=0, to=100, orient='horizontal', command=self._on_volume)
        self._vol.set(80)
        self._vol.grid(row=0, column=7, padx=(6, 0))
        # Keys
        self.bind_all('<space>', lambda e: self._on_play_pause())
        self.bind_all('<Left>', lambda e: self._nudge(-5000))
        self.bind_all('<Right>', lambda e: self._nudge(5000))
        self.bind_all('<Home>', lambda e: self._seek_ms(0))
        self.bind_all('<End>', lambda e: self._jump_to_end())

    # Public API --------------------------------------------------------------
    def set_topic_data(self, topic_element: ET.Element, dita_context: Any) -> None:
        self._topic = topic_element
        self._context = dita_context
        self._videos = getattr(dita_context, 'videos', {}) or {}
        self._populate_items()

    def clear_data(self) -> None:
        self._close_vlc()
        self._topic = None
        self._context = None
        self._videos = {}
        self._items.clear()
        self._list.delete(0, tk.END)
        self._status.set("")
        self._placeholder.configure(text="Select a video to play")

    def cleanup(self) -> None:
        self._close_vlc()
        try:
            for p in list(self._temp_paths.values()):
                try:
                    os.remove(p)
                except Exception:
                    pass
            os.rmdir(self._temp_dir)
        except Exception:
            pass

    # Attempt immediate population if host does not call set_topic_data
    def _maybe_init_from_app_context(self) -> None:
        try:
            if self._context is None and self._app_context and hasattr(self._app_context, 'get_current_dita_context'):
                ctx = self._app_context.get_current_dita_context()
                if ctx is not None:
                    self._context = ctx
                    self._videos = getattr(ctx, 'videos', {}) or {}
                    self._topic = None
                    self._populate_items()
        except Exception:
            pass

    # Internals ---------------------------------------------------------------
    def _populate_items(self) -> None:
        self._close_vlc()
        self._items.clear()
        self._list.delete(0, tk.END)

        # Prefer topic-embedded media: <video> or <object outputclass="video">
        try:
            vids = []
            if self._topic is not None:
                # Collect both legacy <video> and new <object> forms
                try:
                    vids.extend(self._topic.xpath('.//video'))
                except Exception:
                    pass
                try:
                    vids.extend(self._topic.xpath('.//object[contains(@outputclass, "video")]'))
                except Exception:
                    pass
        except Exception:
            vids = []

        for v in vids:
            tag = getattr(v, 'tag', '').lower() if hasattr(v, 'tag') else ''
            href = ''
            if tag == 'video':
                href = str(v.get('href', '') or '')
            else:
                # object: normalize to media/<name>
                data = str(v.get('data', '') or v.get('href', '') or '')
                name_only = Path(data).name if data else ''
                if name_only:
                    href = f'media/{name_only}'
            if href:
                name = Path(href).name
                self._items.append({'display': Path(name).stem, 'filename': name, 'href': href})

        # Strict scoping: do not show context-wide videos when topic has none
        # Leave the list empty to reflect the selected topic accurately

        for item in self._items:
            self._list.insert(tk.END, item['display'])

        if self._items:
            self._list.selection_set(0)
            self._on_select(None)
        else:
            self._placeholder.configure(text="No videos in this topic")

    def _on_select(self, _evt: Optional[Any]) -> None:
        sel = self._list.curselection()
        if not sel:
            return
        item = self._items[int(sel[0])]
        filename = self._strip_media(item['href'])
        data = self._videos.get(filename)
        # Update compact tooltip/status with metadata if available
        try:
            info = {}
            if self._context and hasattr(self._context, 'plugin_data'):
                info = ((self._context.plugin_data or {})
                        .get('orlando-video-plugin', {})
                        .get('video_info_map', {})
                        .get(filename, {}))
            duration = info.get('duration_formatted')
            w = info.get('width')
            h = info.get('height')
            size_mb = info.get('file_size_mb')
            parts = []
            if w and h:
                parts.append(f"{w}x{h}")
            if size_mb is not None:
                try:
                    parts.append(f"{float(size_mb):.1f}MB")
                except Exception:
                    parts.append(f"{size_mb}MB")
            if duration:
                parts.append(str(duration))
            self._status.set(" | ".join(parts))
        except Exception:
            pass
        # Remember position of previously playing file
        try:
            prev = self._current_filename
            if self._vlc_player and prev:
                self._last_pos_ms_by_file[prev] = int(self._vlc_player.get_time() or 0)
        except Exception:
            pass
        self._current_filename = filename
        if not data:
            self._status.set("Media not found in context")
            return
        self._status.set("Loadingâ€¦")
        path = self._temp_paths.get(filename)
        if not path:
            path = os.path.join(self._temp_dir, filename)
            try:
                with open(path, 'wb') as f:
                    f.write(data)
                self._temp_paths[filename] = path
            except Exception as e:
                logger.error("Temp write failed: %s", e)
                self._status.set("Failed to prepare media")
                return
        self._open_vlc(path)

    def _open_vlc(self, path: str) -> None:
        self._close_vlc()
        try:
            import vlc  # type: ignore
        except Exception:
            self._placeholder.configure(text="VLC backend not available (install python-vlc)")
            self._status.set("")
            return
        try:
            # Ensure the surface is realized/mapped before embedding
            try:
                wid = int(self._surface.winfo_id())
            except Exception:
                wid = 0
            if wid == 0 or not self._surface.winfo_ismapped():
                # Defer initialization slightly until the widget is ready
                self.after(100, lambda p=path: self._open_vlc(p))
                return

            self._vlc_instance = vlc.Instance()
            self._vlc_player = self._vlc_instance.media_player_new()
            media = self._vlc_instance.media_new(path)
            self._vlc_player.set_media(media)
            # Embed with platform-specific handle
            try:
                if sys.platform.startswith('win'):
                    self._vlc_player.set_hwnd(wid)
                elif sys.platform == 'darwin':
                    self._vlc_player.set_nsobject(wid)
                else:
                    self._vlc_player.set_xwindow(wid)
            except Exception:
                # If embedding fails, show a message and avoid crashing
                self._placeholder.configure(text="Video preview not embeddable on this system")
                self._status.set("")
                self._vlc_player = None
                self._vlc_instance = None
                return
            # Do not autoplay; pause on first frame for preview
            self._btn_play.configure(text=self.PLAY_ICON)
            self._status.set("Ready")
            self._placeholder.configure(text="")
            # Reset known duration
            self._duration_ms = 0
            # Apply initial audio settings
            try:
                self._vlc_player.audio_set_volume(int(self._vol.get()))
                self._vlc_player.audio_set_mute(bool(self._mute_var.get()))
            except Exception:
                pass
            # Render first frame then restore last position if configured
            try:
                # Kick VLC to render the first frame without playing
                self._prepare_first_frame()
                remember = bool(((self.plugin_config or {}).get('ui_settings', {})
                                  .get('video_preview_panel', {})
                                  .get('remember_positions', True)))
                if remember and self._current_filename in self._last_pos_ms_by_file:
                    pos = int(self._last_pos_ms_by_file[self._current_filename])
                    self.after(150, lambda: self._safe_set_time(pos))
            except Exception:
                pass
        except Exception as e:
            logger.error("VLC open failed: %s", e)
            self._status.set("Cannot open video")

    def _close_vlc(self) -> None:
        try:
            if self._vlc_player:
                try:
                    self._vlc_player.stop()
                except Exception:
                    pass
        except Exception:
            pass
        self._stop_poll()
        self._vlc_player = None
        self._vlc_instance = None
        try:
            self._btn_play.configure(text="Play")
        except Exception:
            pass

    def _on_play_pause(self) -> None:
        if not self._vlc_player:
            return
        try:
            # Use is_playing() for reliable toggle
            if self._vlc_player.is_playing():
                self._vlc_player.pause()
                self._btn_play.configure(text=self.PLAY_ICON)
            else:
                self._vlc_player.play()
                self._btn_play.configure(text=self.PAUSE_ICON)
            self._start_poll()
        except Exception:
            pass

    def _on_stop(self) -> None:
        if not self._vlc_player:
            return
        try:
            self._vlc_player.stop()
            self._btn_play.configure(text=self.PLAY_ICON)
            self._status.set("Ready")
            self._stop_poll()
        except Exception:
            pass

    @staticmethod
    def _strip_media(href: str) -> str:
        return href[6:] if href.startswith('media/') else href

    # ------------------------------------------------------------------
    # Controls that were referenced by UI widgets and keybinds
    # Implement minimal, safe behavior to avoid attribute errors.
    # ------------------------------------------------------------------

    def _on_prev(self) -> None:
        try:
            sel = self._list.curselection()
            if sel:
                i = int(sel[0])
                if i > 0:
                    self._list.selection_clear(0, tk.END)
                    self._list.selection_set(i - 1)
                    self._list.see(i - 1)
                    self._on_select(None)
        except Exception:
            pass

    def _on_next(self) -> None:
        try:
            sel = self._list.curselection()
            if sel:
                i = int(sel[0])
                if i < max(0, len(self._items) - 1):
                    self._list.selection_clear(0, tk.END)
                    self._list.selection_set(i + 1)
                    self._list.see(i + 1)
                    self._on_select(None)
        except Exception:
            pass

    def _get_length_ms(self) -> int:
        try:
            if self._vlc_player:
                length = int(self._vlc_player.get_length() or 0)
                return max(0, length)
        except Exception:
            pass
        return 0

    def _clamp_time(self, ms: int) -> int:
        length = self._get_length_ms()
        if length <= 0:
            return max(0, ms)
        return min(max(0, ms), length)

    def _format_ms(self, ms: int) -> str:
        try:
            s = max(0, int(ms // 1000))
            m, s = divmod(s, 60)
            h, m = divmod(m, 60)
            if h:
                return f"{h:02d}:{m:02d}:{s:02d}"
            return f"{m:02d}:{s:02d}"
        except Exception:
            return "00:00"

    def _update_time_label_from_player(self) -> None:
        try:
            cur = 0
            if self._vlc_player:
                cur = int(self._vlc_player.get_time() or 0)
            total = self._get_length_ms()
            self._lbl_time.configure(text=f"{self._format_ms(cur)} / {self._format_ms(total)}")
        except Exception:
            pass

    def _on_seek(self, value: Any) -> None:
        if not self._vlc_player:
            return
        try:
            # Scale is 0..1000; map to media length
            if self._updating_seek:
                return
            pos = float(value)
            pos = max(0.0, min(1000.0, pos))
            length = self._get_length_ms()
            if length > 0:
                target = int((pos / 1000.0) * length)
                self._vlc_player.set_time(self._clamp_time(target))
                self._update_time_label_from_player()
        except Exception:
            pass

    def _on_seek_click(self, event: Any) -> None:
        try:
            w = event.widget
            width = max(1, int(w.winfo_width()))
            fraction = max(0.0, min(1.0, float(event.x) / float(width)))
            value = int(fraction * 1000)
            self._seek.set(value)
            self._on_seek(value)
        except Exception:
            pass

    def _nudge(self, delta_ms: int) -> None:
        if not self._vlc_player:
            return
        try:
            cur = int(self._vlc_player.get_time() or 0)
            self._vlc_player.set_time(self._clamp_time(cur + int(delta_ms)))
            self._update_time_label_from_player()
        except Exception:
            pass

    def _seek_ms(self, ms: int) -> None:
        if not self._vlc_player:
            return
        try:
            self._vlc_player.set_time(self._clamp_time(int(ms)))
            self._update_time_label_from_player()
        except Exception:
            pass

    def _jump_to_end(self) -> None:
        length = self._get_length_ms()
        if length > 0:
            try:
                self._vlc_player.set_time(self._clamp_time(length - 200))
                self._update_time_label_from_player()
            except Exception:
                pass

    def _on_volume(self, value: Any) -> None:
        if not self._vlc_player:
            return
        try:
            vol = int(float(value))
            vol = max(0, min(100, vol))
            self._vlc_player.audio_set_volume(vol)
        except Exception:
            pass

    def _apply_mute(self) -> None:
        if not self._vlc_player:
            return
        try:
            self._vlc_player.audio_set_mute(bool(self._mute_var.get()))
        except Exception:
            pass

    def _apply_speed(self) -> None:
        if not self._vlc_player:
            return
        try:
            raw = str(self._speed_var.get() or "1.0x")
            m = re.search(r"\d+(?:[\.,]\d+)?", raw)
            rate = 1.0
            if m:
                rate = float(m.group(0).replace(',', '.'))
            self._vlc_player.set_rate(rate)
        except Exception:
            pass

    # -------------------------------
    # Polling and helpers
    # -------------------------------
    def _safe_set_time(self, ms: int) -> None:
        try:
            if self._vlc_player:
                self._vlc_player.set_time(self._clamp_time(int(ms)))
        except Exception:
            pass

    def _prepare_first_frame(self) -> None:
        """Start-stop quickly so the first frame is rendered but remain paused."""
        try:
            if not self._vlc_player:
                return
            # Start briefly to force video surface to render
            self._vlc_player.play()
            def _pause_at_zero() -> None:
                try:
                    self._vlc_player.set_time(0)
                    self._vlc_player.pause()
                    self._btn_play.configure(text=self.PLAY_ICON)
                    # Update time label/seek
                    self._update_time_label_from_player()
                    self._updating_seek = True
                    try:
                        self._seek.set(0)
                    finally:
                        self._updating_seek = False
                except Exception:
                    pass
            self.after(200, _pause_at_zero)
        except Exception:
            pass

    def _set_user_seeking(self, seeking: bool) -> None:
        self._user_seeking = bool(seeking)

    def _get_poll_interval(self) -> int:
        try:
            return int(((self.plugin_config or {}).get('ui_settings', {})
                        .get('video_preview_panel', {})
                        .get('poll_interval_ms', 200)))
        except Exception:
            return 200

    def _start_poll(self) -> None:
        if self._poll_job is not None:
            return
        self._poll_job = self.after(self._get_poll_interval(), self._poll)

    def _stop_poll(self) -> None:
        try:
            if self._poll_job is not None:
                self.after_cancel(self._poll_job)
        except Exception:
            pass
        self._poll_job = None

    def _poll(self) -> None:
        try:
            if self._vlc_player:
                # Update duration lazily once available
                if self._duration_ms <= 0:
                    dur = int(self._vlc_player.get_length() or 0)
                    if dur > 0:
                        self._duration_ms = dur
                # Update time label
                self._update_time_label_from_player()
                # Update seek position if user isn't dragging
                if not self._user_seeking:
                    total = self._duration_ms if self._duration_ms > 0 else self._get_length_ms()
                    if total > 0:
                        cur = int(self._vlc_player.get_time() or 0)
                        pos = int((cur / max(1, total)) * 1000)
                        self._updating_seek = True
                        try:
                            self._seek.set(max(0, min(1000, pos)))
                        finally:
                            self._updating_seek = False
        except Exception:
            pass
        # Reschedule
        self._poll_job = self.after(self._get_poll_interval(), self._poll)
