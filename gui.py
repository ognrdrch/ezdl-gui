import os
import sys
from pathlib import Path
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFrame, QTextEdit, QProgressBar, QApplication,
    QSizePolicy, QSpacerItem
)
from PyQt5.QtCore import Qt, QPoint, QTimer, QPropertyAnimation, QEasingCurve, pyqtSignal, QRect
from PyQt5.QtGui import (
    QColor, QPainter, QBrush, QPen, QFont, QLinearGradient,
    QPainterPath, QPixmap, QFontDatabase
)

from config import load_settings, save_settings, VERSION
from downloader import DownloadWorker
from updater import UpdateWorker, get_ytdlp_version
from settings_window import SettingsWindow


ACCENT = "#5B8AF0"
BG_DEEP = "#07070F"
BG_CARD = "#0E0E1A"
BG_SURFACE = "#141422"
BG_RAISED = "#1C1C2E"
BORDER = "#1E1E30"
TEXT_PRI = "#E8E8F4"
TEXT_SEC = "#9090A8"
TEXT_DIM = "#555566"
SUCCESS = "#3DD68C"
ERROR = "#E74C3C"
WARNING = "#F0A500"


class AnimatedButton(QPushButton):
    def __init__(self, text, accent=False, parent=None):
        super().__init__(text, parent)
        self.accent = accent
        self._anim_val = 0
        self.setFixedHeight(42)
        self._update_style()

    def _update_style(self):
        if self.accent:
            self.setStyleSheet(f"""
                QPushButton {{
                    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                        stop:0 #5B8AF0, stop:1 #7B6FEF);
                    color: white;
                    border: none;
                    border-radius: 10px;
                    font-size: 13px;
                    font-weight: 600;
                    letter-spacing: 0.3px;
                }}
                QPushButton:hover {{
                    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                        stop:0 #6B9AFF, stop:1 #8B7FFF);
                }}
                QPushButton:pressed {{
                    background: #4A79E0;
                }}
                QPushButton:disabled {{
                    background: #252535;
                    color: #555;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background: {BG_RAISED};
                    color: {TEXT_SEC};
                    border: 1px solid {BORDER};
                    border-radius: 10px;
                    font-size: 13px;
                    font-weight: 500;
                }}
                QPushButton:hover {{
                    background: #242436;
                    color: {TEXT_PRI};
                    border-color: #2E2E44;
                }}
                QPushButton:pressed {{
                    background: #1A1A28;
                }}
                QPushButton:disabled {{
                    background: #111120;
                    color: #333;
                    border-color: #181828;
                }}
            """)


class StatusDot(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(8, 8)
        self._color = QColor(SUCCESS)
        self._blink = False
        self._blink_state = True
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._toggle_blink)

    def set_state(self, state):  # "idle", "downloading", "success", "error"
        self._timer.stop()
        if state == "idle":
            self._color = QColor(TEXT_DIM)
            self._blink = False
        elif state == "downloading":
            self._color = QColor(WARNING)
            self._blink = True
            self._timer.start(500)
        elif state == "success":
            self._color = QColor(SUCCESS)
            self._blink = False
        elif state == "error":
            self._color = QColor(ERROR)
            self._blink = False
        self.update()

    def _toggle_blink(self):
        self._blink_state = not self._blink_state
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        color = self._color if (not self._blink or self._blink_state) else QColor(BG_SURFACE)
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(0, 0, 8, 8)


class LogPanel(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMaximumHeight(140)
        self.setMinimumHeight(80)
        self.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_DEEP};
                color: {TEXT_DIM};
                border: 1px solid {BORDER};
                border-radius: 8px;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 11px;
                padding: 8px;
            }}
            QScrollBar:vertical {{
                background: {BG_DEEP};
                width: 4px;
                border-radius: 2px;
            }}
            QScrollBar::handle:vertical {{
                background: #2A2A3A;
                border-radius: 2px;
                min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)

    def append_line(self, text, color=None):
        if color:
            self.append(f'<span style="color:{color};">{text}</span>')
        else:
            self.append(text)
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())


class GlowProgressBar(QProgressBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(4)
        self.setTextVisible(False)
        self.setStyleSheet(f"""
            QProgressBar {{
                background: {BG_SURFACE};
                border-radius: 2px;
                border: none;
            }}
            QProgressBar::chunk {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #5B8AF0, stop:1 #7B6FEF);
                border-radius: 2px;
            }}
        """)


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.settings = load_settings()
        self.settings_win = None
        self.download_worker = None
        self.drag_pos = QPoint()

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setMinimumSize(480, 500)
        self.resize(500, 560)
        self.setWindowTitle("EZDL")

        self._init_ui()
        self._check_ytdlp_version()

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Main card ─────────────────────────────────────
        self.card = QFrame(self)
        self.card.setObjectName("mainCard")
        self.card.setStyleSheet(f"""
            QFrame#mainCard {{
                background-color: {BG_CARD};
                border: none;
                border-radius: 0px;
            }}
            QWidget {{
                background-color: {BG_CARD};
            }}
        """)
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        # ── Title bar ─────────────────────────────────────
        title_bar = QFrame()
        title_bar.setFixedHeight(56)
        title_bar.setStyleSheet("background: transparent;")
        tb_layout = QHBoxLayout(title_bar)
        tb_layout.setContentsMargins(20, 0, 14, 0)

        # Logo + title
        logo_row = QHBoxLayout()
        logo_row.setSpacing(8)

        self.status_dot = StatusDot()
        self.status_dot.set_state("idle")
        logo_row.addWidget(self.status_dot)

        title_lbl = QLabel("EZDL")
        title_lbl.setStyleSheet(f"""
            color: {TEXT_PRI};
            font-size: 15px;
            font-weight: 700;
            letter-spacing: 1px;
        """)
        logo_row.addWidget(title_lbl)

        self.version_lbl = QLabel(f"v{VERSION}")
        self.version_lbl.setStyleSheet(f"color: {TEXT_DIM}; font-size: 10px; margin-top: 3px;")
        logo_row.addWidget(self.version_lbl)

        tb_layout.addLayout(logo_row)
        tb_layout.addStretch()

        # Header buttons
        self.update_btn = self._icon_btn("↻", "Update yt-dlp")
        self.update_btn.clicked.connect(self._run_update)
        self.settings_btn = self._icon_btn("⚙", "Settings")
        self.settings_btn.clicked.connect(self._open_settings)
        self.minimize_btn = self._icon_btn("−", "Minimize")
        self.minimize_btn.clicked.connect(self.showMinimized)
        self.close_btn = self._icon_btn("✕", "Close")
        self.close_btn.setStyleSheet(self.close_btn.styleSheet().replace(
            "color: #888", "color: #888"
        ))
        self.close_btn.clicked.connect(self.close)
        self.close_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #666;
                border: none;
                border-radius: 12px;
                font-size: 13px;
                width: 24px; height: 24px;
            }
            QPushButton:hover { background: #E74C3C; color: white; }
        """)

        for b in [self.update_btn, self.settings_btn, self.minimize_btn]:
            tb_layout.addWidget(b)
        tb_layout.addSpacing(4)
        tb_layout.addWidget(self.close_btn)

        card_layout.addWidget(title_bar)

        # ── Divider ───────────────────────────────────────
        div = QFrame()
        div.setFixedHeight(1)
        div.setStyleSheet(f"background: {BORDER};")
        card_layout.addWidget(div)

        # ── Body ──────────────────────────────────────────
        body = QWidget()
        body.setStyleSheet("background: transparent;")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(24, 24, 24, 24)
        body_layout.setSpacing(16)

        # URL input section
        url_label = QLabel("Media URL")
        url_label.setStyleSheet(f"""
            color: {TEXT_DIM};
            font-size: 10px;
            font-weight: 600;
            letter-spacing: 1.5px;
        """)
        #body_layout.addWidget(url_label)

        url_row = QHBoxLayout()
        url_row.setSpacing(8)

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Paste a Media URL")
        self.url_input.setFixedHeight(46)
        self.url_input.setStyleSheet(f"""
            QLineEdit {{
                background: {BG_SURFACE};
                color: {TEXT_PRI};
                border: 1px solid {BORDER};
                border-radius: 10px;
                padding: 0 14px;
                font-size: 13px;
            }}
            QLineEdit:focus {{
                border-color: {ACCENT};
                background: #161628;
            }}
            QLineEdit::placeholder {{
                color: {TEXT_DIM};
            }}
        """)
        self.url_input.returnPressed.connect(self._smart_download)
        url_row.addWidget(self.url_input)

        paste_btn = QPushButton("Paste")
        paste_btn.setFixedHeight(46)
        paste_btn.setFixedWidth(60)
        paste_btn.setStyleSheet(f"""
            QPushButton {{
                background: {BG_SURFACE};
                color: {TEXT_SEC};
                border: 1px solid {BORDER};
                border-radius: 10px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background: {BG_RAISED};
                color: {TEXT_PRI};
            }}
        """)
        paste_btn.clicked.connect(lambda: self.url_input.setText(
            QApplication.clipboard().text()
        ))
        url_row.addWidget(paste_btn)
        body_layout.addLayout(url_row)

        # Download buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.audio_btn = AnimatedButton("♫  Download Audio", accent=True)
        self.video_btn = AnimatedButton("▶  Download Video", accent=False)

        self.audio_btn.clicked.connect(lambda: self._start_download("audio"))
        self.video_btn.clicked.connect(lambda: self._start_download("video"))

        btn_row.addWidget(self.audio_btn)
        btn_row.addWidget(self.video_btn)
        body_layout.addLayout(btn_row)

        # Cancel button
        self.cancel_btn = QPushButton("✕  Cancel Download")
        self.cancel_btn.setFixedHeight(32)
        self.cancel_btn.hide()
        self.cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {ERROR};
                border: 1px solid #3A1A1A;
                border-radius: 8px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background: #2A0A0A;
                border-color: {ERROR};
            }}
        """)
        self.cancel_btn.clicked.connect(self._cancel_download)
        body_layout.addWidget(self.cancel_btn)

        # Progress bar
        self.progress_bar = GlowProgressBar()
        self.progress_bar.hide()
        body_layout.addWidget(self.progress_bar)

        # Status line
        self.status_lbl = QLabel("Ready")
        self.status_lbl.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px;")
        self.status_lbl.setAlignment(Qt.AlignCenter)
        self.status_lbl.setFixedHeight(16)
        body_layout.addWidget(self.status_lbl)

        # ── Divider ───────────────────────────────────────
        div2 = QFrame()
        div2.setFixedHeight(1)
        div2.setStyleSheet(f"background: {BORDER};")
        body_layout.addWidget(div2)

        # Log panel toggle
        log_header = QHBoxLayout()
        log_lbl = QLabel("LOG")
        log_lbl.setStyleSheet(f"color: {TEXT_DIM}; font-size: 10px; letter-spacing: 1.5px;")
        log_header.addWidget(log_lbl)
        log_header.addStretch()

        self.clear_log_btn = QPushButton("Clear")
        self.clear_log_btn.setFixedHeight(20)
        self.clear_log_btn.setFixedWidth(44)
        self.clear_log_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {TEXT_DIM};
                border: none;
                font-size: 10px;
            }}
            QPushButton:hover {{ color: {TEXT_SEC}; }}
        """)
        self.clear_log_btn.clicked.connect(lambda: self.log.clear())
        log_header.addWidget(self.clear_log_btn)
        body_layout.addLayout(log_header)

        self.log = LogPanel()
        self.log.append_line("EZDL ready. Paste a URL to get started.", TEXT_DIM)
        body_layout.addWidget(self.log)

        card_layout.addWidget(body)
        root.addWidget(self.card)

    # ── Helper UI factories ───────────────────────────────

    def _icon_btn(self, icon, tooltip):
        btn = QPushButton(icon)
        btn.setFixedSize(28, 28)
        btn.setToolTip(tooltip)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {TEXT_DIM};
                border: none;
                border-radius: 8px;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background: {BG_RAISED};
                color: {TEXT_SEC};
            }}
        """)
        return btn

    # ── Core functionality ────────────────────────────────

    def _smart_download(self):
        """Guess audio vs video from URL and start the appropriate download."""
        url = self.url_input.text().strip()
        if not url:
            return
        # Default to audio for known music-only sites, video for everything else
        music_sites = ["spotify", "soundcloud", "bandcamp", "music.youtube"]
        mode = "audio" if any(s in url.lower() for s in music_sites) else "video"
        self._start_download(mode)

    def _start_download(self, mode: str):
        url = self.url_input.text().strip()
        if not url:
            self._set_status("Please enter a URL.", ERROR)
            return
        if self.download_worker and self.download_worker.isRunning():
            self._set_status("Already downloading. Cancel first.", WARNING)
            return

        self.settings = load_settings()  # Reload fresh settings
        self._set_downloading(True)
        self.status_dot.set_state("downloading")
        self.log.append_line(f"\n{'─'*40}", TEXT_DIM)
        self.log.append_line(f"Starting {mode} download…", ACCENT)
        self.progress_bar.setValue(0)
        self.progress_bar.show()

        self.download_worker = DownloadWorker(url, mode, self.settings)
        self.download_worker.progress.connect(self._on_log)
        self.download_worker.percent.connect(self._on_percent)
        self.download_worker.finished.connect(self._on_finished)
        self.download_worker.start()

    def _cancel_download(self):
        if self.download_worker:
            self.download_worker.cancel()

    def _on_log(self, text):
        # Color-code key lines
        if "[download]" in text:
            color = ACCENT
        elif "error" in text.lower() or "ERROR" in text:
            color = ERROR
        elif "warning" in text.lower():
            color = WARNING
        elif "Destination" in text or "Merging" in text:
            color = SUCCESS
        else:
            color = TEXT_DIM
        self.log.append_line(text, color)

    def _on_percent(self, pct):
        self.progress_bar.setValue(int(pct))
        self._set_status(f"Downloading… {pct:.1f}%", TEXT_SEC)

    def _on_finished(self, success, message):
        self._set_downloading(False)
        self.progress_bar.hide()
        if success:
            self.status_dot.set_state("success")
            self._set_status(f"✓  {message}", SUCCESS)
            self.log.append_line(f"✓ {message}", SUCCESS)
            # Reset dot after 4 seconds
            QTimer.singleShot(4000, lambda: self.status_dot.set_state("idle"))
        else:
            self.status_dot.set_state("error")
            self._set_status(f"✗  {message}", ERROR)
            self.log.append_line(f"✗ {message}", ERROR)
            QTimer.singleShot(6000, lambda: self.status_dot.set_state("idle"))

    def _set_downloading(self, active: bool):
        self.audio_btn.setEnabled(not active)
        self.video_btn.setEnabled(not active)
        self.cancel_btn.setVisible(active)
        if not active:
            self._set_status("Ready", TEXT_DIM)

    def _set_status(self, text, color=None):
        style = f"font-size: 12px; color: {color or TEXT_DIM};"
        self.status_lbl.setStyleSheet(style)
        self.status_lbl.setText(text)

    def _check_ytdlp_version(self):
        ver = get_ytdlp_version()
        self.log.append_line(f"yt-dlp version: {ver}", TEXT_DIM)
        if ver == "not found":
            self._set_status("yt-dlp not found — click ↻ to install", WARNING)
            self.log.append_line("⚠ yt-dlp not found. Click ↻ to install it.", WARNING)

    def _run_update(self):
        self.update_btn.setEnabled(False)
        self.log.append_line("\nChecking for updates…", TEXT_DIM)
        self._set_status("Updating yt-dlp…", ACCENT)

        self._update_worker = UpdateWorker("ytdlp")
        self._update_worker.log.connect(lambda t: self.log.append_line(t, TEXT_DIM))
        self._update_worker.finished.connect(self._on_update_done)
        self._update_worker.start()

    def _on_update_done(self, success, message):
        self.update_btn.setEnabled(True)
        color = SUCCESS if success else ERROR
        self.log.append_line(message, color)
        self._set_status(message, color)
        # Refresh version display
        QTimer.singleShot(500, self._check_ytdlp_version)

    def _open_settings(self):
        if self.settings_win and self.settings_win.isVisible():
            self.settings_win.raise_()
            return
        self.settings = load_settings()
        self.settings_win = SettingsWindow(self.settings, self)
        self.settings_win.settings_saved.connect(self._on_settings_saved)
        # Position near main window
        geo = self.geometry()
        self.settings_win.move(geo.x() + geo.width() + 10, geo.y())
        self.settings_win.show()

    def _on_settings_saved(self, new_settings):
        self.settings = new_settings
        self.log.append_line("Settings saved.", SUCCESS)

    # ── Window dragging ───────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and event.y() < 56:
            self.drag_pos = event.globalPos() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self.drag_pos:
            self.move(event.globalPos() - self.drag_pos)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        # Subtle outer glow / shadow
        painter.fillRect(self.rect(), Qt.transparent)
