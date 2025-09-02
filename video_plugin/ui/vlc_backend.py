from __future__ import annotations

"""Minimal VLC backend for embedding playback in a Tkinter widget.

This is a small, optional PoC backend used by the VideoPreviewPanel.
It requires python-vlc and a loadable libVLC on the host machine.
"""

from typing import Optional, Any
import sys


class VLCBackend:
    def __init__(self) -> None:
        self._vlc = None
        self._instance = None
        self._player = None
        self._media = None
        self._widget: Optional[Any] = None

    @staticmethod
    def is_available() -> bool:
        try:
            import vlc  # type: ignore
            _ = vlc.Instance()
            return True
        except Exception:
            return False

    def open(self, media_path: str, widget: Any) -> bool:
        try:
            import vlc  # type: ignore
            self._vlc = vlc
            self._instance = vlc.Instance()
            self._player = self._instance.media_player_new()
            self._media = self._instance.media_new(media_path)
            self._player.set_media(self._media)
            self._widget = widget

            wid = int(widget.winfo_id())
            if sys.platform.startswith('win'):
                self._player.set_hwnd(wid)
            elif sys.platform == 'darwin':
                self._player.set_nsobject(wid)
            else:
                self._player.set_xwindow(wid)
            return True
        except Exception:
            self.close()
            return False

    def play(self) -> None:
        try:
            if self._player:
                self._player.play()
        except Exception:
            pass

    def pause(self) -> None:
        try:
            if self._player:
                self._player.pause()
        except Exception:
            pass

    def stop(self) -> None:
        try:
            if self._player:
                self._player.stop()
        except Exception:
            pass

    def set_speed(self, rate: float) -> None:
        try:
            if self._player and rate > 0:
                self._player.set_rate(rate)
        except Exception:
            pass

    def seek_ms(self, ms: int) -> None:
        try:
            if self._player:
                self._player.set_time(int(ms))
        except Exception:
            pass

    def get_pos_ms(self) -> int:
        try:
            if self._player:
                return int(self._player.get_time())
        except Exception:
            pass
        return 0

    def get_duration_ms(self) -> int:
        try:
            if self._player:
                return int(self._player.get_length())
        except Exception:
            pass
        return 0

    def has_audio(self) -> bool:
        return True

    def close(self) -> None:
        try:
            if self._player:
                try:
                    self._player.stop()
                except Exception:
                    pass
            self._player = None
            self._media = None
            self._instance = None
            self._vlc = None
            self._widget = None
        except Exception:
            pass

