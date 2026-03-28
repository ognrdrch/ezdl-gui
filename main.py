import sys
import os
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

# Ensure the app directory is in path
sys.path.insert(0, os.path.dirname(__file__))

# ── Windows taskbar fix ───────────────────────────────────────────────────────
# Without an explicit AppUserModelID Windows groups the window under the Python
# interpreter icon instead of showing our custom icon in the taskbar.
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ezdl.app.2")
    except Exception:
        pass

from gui import MainWindow


def _load_icon() -> QIcon:
    """
    Try to load icon512.png next to the executable / script.
    Falls back gracefully if the file is missing.
    """
    base = os.path.dirname(os.path.abspath(
        sys.executable if getattr(sys, "frozen", False) else __file__
    ))
    for name in ("icon512.png", "icon256.png", "icon128.png", "icon.png"):
        path = os.path.join(base, name)
        if os.path.exists(path):
            return QIcon(path)
    return QIcon()


def main():
    # Enable HiDPI support
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("EZDL")
    app.setApplicationVersion("2.0.0")

    icon = _load_icon()
    app.setWindowIcon(icon)

    window = MainWindow()
    # Set icon on the window itself — required for the taskbar button on Windows
    # and for window-switcher / dock entries on Linux desktops.
    window.setWindowIcon(icon)
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

