import os
import sys
from pathlib import Path
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QCheckBox, QComboBox, QFileDialog, QSlider,
    QFrame, QSizePolicy, QSpacerItem
)
from PyQt5.QtCore import Qt, QPoint, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QBrush, QFont, QPen, QCursor

from config import save_settings, SETTINGS_PATH
import toml


BROWSERS = ["brave", "chrome", "firefox", "chromium", "edge", "opera", "safari", "vivaldi"]


class SectionLabel(QLabel):
    def __init__(self, text, parent=None):
        super().__init__(text.upper(), parent)
        self.setStyleSheet("""
            QLabel {
                color: #5B8AF0;
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 2px;
                padding: 0;
                margin-top: 12px;
            }
        """)


class ModernSlider(QSlider):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 4px;
                background: #2A2A3A;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #5B8AF0;
                width: 14px; height: 14px;
                margin: -5px 0;
                border-radius: 7px;
            }
            QSlider::sub-page:horizontal {
                background: #5B8AF0;
                border-radius: 2px;
            }
        """)


class SettingsWindow(QWidget):
    settings_saved = pyqtSignal(dict)

    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.settings = settings
        self._parent = parent
        self.drag_pos = QPoint()

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumWidth(500)
        self._init_ui()
        self.adjustSize()

    def _init_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        card = QFrame(self)
        card.setObjectName("settingsCard")
        card.setStyleSheet(f"""
            QFrame#settingsCard {{
                background-color: #0E0E18;
                border: none;
                border-radius: 0px;
            }}
            QWidget {{
                background-color: #0E0E18;
            }}
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        # Title bar
        title_bar = QFrame()
        title_bar.setFixedHeight(52)
        title_bar.setStyleSheet("background: transparent;")
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(20, 0, 12, 0)

        title = QLabel("Settings")
        title.setStyleSheet("color: #E8E8F0; font-size: 14px; font-weight: 600;")
        title_layout.addWidget(title)
        title_layout.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setStyleSheet("""
            QPushButton {
                background: #2A2A3A;
                color: #888;
                border: none;
                border-radius: 14px;
                font-size: 11px;
            }
            QPushButton:hover { background: #E74C3C; color: white; }
        """)
        close_btn.clicked.connect(self.close)
        title_layout.addWidget(close_btn)
        card_layout.addWidget(title_bar)

        # Divider
        div = QFrame()
        div.setFixedHeight(1)
        div.setStyleSheet("background: #1E1E2E;")
        card_layout.addWidget(div)

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(24, 16, 24, 24)
        content_layout.setSpacing(6)

        s = self.settings.get("settings", {})

        # ── PATHS ──────────────────────────────────────────
        content_layout.addWidget(SectionLabel("Download Paths"))
        self.audio_path = self._path_row("Audio Path", s.get("audio_path", ""), self._browse_audio)
        content_layout.addLayout(self.audio_path["layout"])

        self.video_path_w = self._path_row("Video Path", s.get("video_path", ""), self._browse_video)
        content_layout.addLayout(self.video_path_w["layout"])

        # ── FILE NAMING ────────────────────────────────────
        content_layout.addWidget(SectionLabel("File Naming"))
        naming = s.get("file_naming_scheme", "%(title)s.%(ext)s")
        naming_layout = QHBoxLayout()
        naming_layout.setSpacing(8)
        self.naming_title = self._chip("Title", "%(title)s" in naming)
        self.naming_uploader = self._chip("Uploader", "%(uploader)s" in naming)
        self.naming_date = self._chip("Date", "%(upload_date)s" in naming)
        self.naming_id = self._chip("ID", "%(id)s" in naming)
        for chip in [self.naming_title, self.naming_uploader, self.naming_date, self.naming_id]:
            naming_layout.addWidget(chip)
        naming_layout.addStretch()
        content_layout.addLayout(naming_layout)

        # ── FORMATS ────────────────────────────────────────
        content_layout.addWidget(SectionLabel("Formats"))
        fmt_layout = QHBoxLayout()
        fmt_layout.setSpacing(12)

        audio_col = QVBoxLayout()
        audio_col.addWidget(self._mini_label("Audio Format"))
        self.audio_format = QComboBox()
        self.audio_format.addItems(["mp3", "aac", "flac", "wav", "opus", "m4a"])
        self.audio_format.setCurrentText(s.get("audio_format", "flac"))
        self._style_combo(self.audio_format)
        audio_col.addWidget(self.audio_format)

        video_col = QVBoxLayout()
        video_col.addWidget(self._mini_label("Video Format"))
        self.video_format = QComboBox()
        self.video_format.addItems(["mp4", "mkv", "avi", "mov", "webm"])
        self.video_format.setCurrentText(s.get("video_format", "mp4"))
        self._style_combo(self.video_format)
        video_col.addWidget(self.video_format)

        fmt_layout.addLayout(audio_col)
        fmt_layout.addLayout(video_col)
        content_layout.addLayout(fmt_layout)

        # ── AUDIO QUALITY ──────────────────────────────────
        content_layout.addWidget(SectionLabel("Audio Quality"))
        qual_row = QHBoxLayout()
        self.quality_label = QLabel(f"Best (0)  ←  {s.get('audio_quality', 0)}  →  Worst (10)")
        self.quality_label.setStyleSheet("color: #888; font-size: 11px;")
        qual_row.addWidget(self.quality_label)
        content_layout.addLayout(qual_row)

        self.quality_slider = ModernSlider(Qt.Horizontal)
        self.quality_slider.setRange(0, 10)
        self.quality_slider.setValue(int(s.get("audio_quality", 0)))
        self.quality_slider.valueChanged.connect(
            lambda v: self.quality_label.setText(f"Best (0)  ←  {v}  →  Worst (10)")
        )
        content_layout.addWidget(self.quality_slider)

        # ── OPTIONS ────────────────────────────────────────
        content_layout.addWidget(SectionLabel("Options"))
        self.dl_playlist = self._toggle("Download full playlists", s.get("download_playlist", False))
        self.embed_thumb = self._toggle("Embed thumbnail in audio files", s.get("embed_thumbnail", True))
        self.embed_meta = self._toggle("Embed metadata", s.get("embed_metadata", True))
        self.use_cookies = self._toggle("Use browser cookies (for members-only content)", s.get("use_cookies", False))
        for w in [self.dl_playlist, self.embed_thumb, self.embed_meta, self.use_cookies]:
            content_layout.addWidget(w)

        # Browser selector (shown when cookies enabled)
        browser_row = QHBoxLayout()
        browser_row.setContentsMargins(28, 0, 0, 0)
        browser_row.addWidget(self._mini_label("Browser:"))
        self.browser_combo = QComboBox()
        self.browser_combo.addItems(BROWSERS)
        self.browser_combo.setCurrentText(s.get("cookie_browser", "brave"))
        self._style_combo(self.browser_combo)
        self.browser_combo.setFixedWidth(140)
        browser_row.addWidget(self.browser_combo)
        browser_row.addStretch()
        content_layout.addLayout(browser_row)

        # Show/hide browser row based on cookies toggle
        def update_browser_visibility(checked):
            self.browser_combo.setVisible(checked)
        self.use_cookies.toggled.connect(update_browser_visibility)
        self.browser_combo.setVisible(s.get("use_cookies", False))

        # ── SPOTIFY ────────────────────────────────────────
        content_layout.addWidget(SectionLabel("Spotify (optional)"))
        so = self.settings.get("other", {})
        self.spotify_id = self._text_input("Client ID", so.get("spotify_id", ""))
        self.spotify_secret = self._text_input("Client Secret", so.get("spotify_secret", ""))
        self.spotify_secret.setEchoMode(QLineEdit.Password)
        content_layout.addWidget(self.spotify_id)
        content_layout.addWidget(self.spotify_secret)

        card_layout.addWidget(content)

        # Save button
        save_bar = QFrame()
        save_bar.setStyleSheet("background: #0A0A14; border-top: 1px solid #1E1E2E;")
        save_layout = QHBoxLayout(save_bar)
        save_layout.setContentsMargins(24, 12, 24, 12)
        save_layout.addStretch()
        save_btn = QPushButton("Save Settings")
        save_btn.setFixedHeight(38)
        save_btn.setFixedWidth(140)
        save_btn.setStyleSheet("""
            QPushButton {
                background: #5B8AF0;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton:hover { background: #7AA3FF; }
            QPushButton:pressed { background: #4A79E0; }
        """)
        save_btn.clicked.connect(self._save)
        save_layout.addWidget(save_btn)
        card_layout.addWidget(save_bar)

        outer.addWidget(card)

    # ── Helpers ──────────────────────────────────────────────

    def _mini_label(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #666; font-size: 11px;")
        return lbl

    def _path_row(self, label, value, browse_fn):
        layout = QVBoxLayout()
        layout.setSpacing(4)
        layout.addWidget(self._mini_label(label))
        row = QHBoxLayout()
        row.setSpacing(6)
        edit = QLineEdit(value)
        edit.setStyleSheet("""
            QLineEdit {
                background: #161622;
                color: #C8C8D8;
                border: 1px solid #252535;
                border-radius: 7px;
                padding: 7px 10px;
                font-size: 12px;
            }
            QLineEdit:focus { border-color: #5B8AF0; }
        """)
        btn = QPushButton("Browse")
        btn.setFixedWidth(70)
        btn.setFixedHeight(32)
        btn.setStyleSheet("""
            QPushButton {
                background: #1E1E2E;
                color: #888;
                border: 1px solid #252535;
                border-radius: 7px;
                font-size: 11px;
            }
            QPushButton:hover { background: #252535; color: #CCC; }
        """)
        btn.clicked.connect(browse_fn)
        row.addWidget(edit)
        row.addWidget(btn)
        layout.addLayout(row)
        return {"layout": layout, "edit": edit}

    def _chip(self, text, checked):
        btn = QPushButton(text)
        btn.setCheckable(True)
        btn.setChecked(checked)
        btn.setFixedHeight(28)
        btn.setStyleSheet("""
            QPushButton {
                background: #1A1A2A;
                color: #666;
                border: 1px solid #252535;
                border-radius: 6px;
                font-size: 11px;
                padding: 0 12px;
            }
            QPushButton:checked {
                background: #1E2B4A;
                color: #5B8AF0;
                border-color: #5B8AF0;
            }
            QPushButton:hover { color: #CCC; }
        """)
        return btn

    def _toggle(self, text, checked):
        cb = QCheckBox(text)
        cb.setChecked(checked)
        cb.setStyleSheet("""
            QCheckBox {
                color: #AAA;
                font-size: 12px;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 16px; height: 16px;
                border-radius: 4px;
                border: 1px solid #333;
                background: #161622;
            }
            QCheckBox::indicator:checked {
                background: #5B8AF0;
                border-color: #5B8AF0;
            }
        """)
        return cb

    def _text_input(self, placeholder, value):
        edit = QLineEdit(value if value not in ("client_id", "client_secret", "") else "")
        edit.setPlaceholderText(placeholder)
        edit.setStyleSheet("""
            QLineEdit {
                background: #161622;
                color: #C8C8D8;
                border: 1px solid #252535;
                border-radius: 7px;
                padding: 7px 10px;
                font-size: 12px;
            }
            QLineEdit:focus { border-color: #5B8AF0; }
        """)
        return edit

    def _style_combo(self, combo):
        combo.setStyleSheet("""
            QComboBox {
                background: #161622;
                color: #C8C8D8;
                border: 1px solid #252535;
                border-radius: 7px;
                padding: 5px 10px;
                font-size: 12px;
            }
            QComboBox::drop-down { border: none; width: 24px; }
            QComboBox::down-arrow { image: none; }
            QComboBox QAbstractItemView {
                background: #1A1A2A;
                color: #C8C8D8;
                selection-background-color: #252545;
                border: 1px solid #252535;
            }
        """)

    def _browse_audio(self):
        # Expand ~ before passing to Qt — on Windows Qt won't expand it and the
        # dialog opens at an invalid path (or falls back to the desktop).
        start = os.path.expanduser(self.audio_path["edit"].text())
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Audio Folder",
            start,
            QFileDialog.ShowDirsOnly
        )
        if folder:
            # Qt returns forward slashes on all platforms; normalize to the OS
            # separator so the displayed path matches what users expect.
            self.audio_path["edit"].setText(os.path.normpath(folder))

    def _browse_video(self):
        start = os.path.expanduser(self.video_path_w["edit"].text())
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Video Folder",
            start,
            QFileDialog.ShowDirsOnly
        )
        if folder:
            self.video_path_w["edit"].setText(os.path.normpath(folder))
    def _build_naming_scheme(self):
        parts = []
        if self.naming_title.isChecked():
            parts.append("%(title)s")
        if self.naming_uploader.isChecked():
            parts.append("%(uploader)s")
        if self.naming_date.isChecked():
            parts.append("%(upload_date)s")
        if self.naming_id.isChecked():
            parts.append("%(id)s")
        if not parts:
            parts = ["%(title)s"]
        return "_".join(parts) + ".%(ext)s"

    def _save(self):
        self.settings["settings"]["audio_path"] = self.audio_path["edit"].text()
        self.settings["settings"]["video_path"] = self.video_path_w["edit"].text()
        self.settings["settings"]["file_naming_scheme"] = self._build_naming_scheme()
        self.settings["settings"]["audio_quality"] = self.quality_slider.value()
        self.settings["settings"]["audio_format"] = self.audio_format.currentText()
        self.settings["settings"]["video_format"] = self.video_format.currentText()
        self.settings["settings"]["download_playlist"] = self.dl_playlist.isChecked()
        self.settings["settings"]["embed_thumbnail"] = self.embed_thumb.isChecked()
        self.settings["settings"]["embed_metadata"] = self.embed_meta.isChecked()
        self.settings["settings"]["use_cookies"] = self.use_cookies.isChecked()
        self.settings["settings"]["cookie_browser"] = self.browser_combo.currentText()

        sid = self.spotify_id.text().strip()
        ssec = self.spotify_secret.text().strip()
        if sid:
            self.settings["other"]["spotify_id"] = sid
        if ssec:
            self.settings["other"]["spotify_secret"] = ssec

        save_settings(self.settings)
        self.settings_saved.emit(self.settings)
        self.close()

    # ── Window dragging ──────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_pos = event.globalPos() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self.drag_pos:
            self.move(event.globalPos() - self.drag_pos)

    def resizeEvent(self, event):
        """Apply a rounded-rectangle mask so the OS clips the window shape."""
        super().resizeEvent(event)
        from PyQt5.QtGui import QRegion, QBitmap, QPainterPath
        from PyQt5.QtCore import Qt
        from PyQt5.QtGui import QPainter
        radius = 12
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), radius, radius)
        mask_bitmap = QBitmap(self.size())
        mask_bitmap.fill(Qt.color0)
        p = QPainter(mask_bitmap)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(Qt.color1)
        p.setPen(Qt.NoPen)
        p.drawPath(path)
        p.end()
        self.setMask(QRegion(mask_bitmap))

    def paintEvent(self, event):
        from PyQt5.QtGui import QPainter, QBrush, QColor
        from PyQt5.QtCore import Qt
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QBrush(QColor("#0E0E18")))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(self.rect(), 12, 12)
