import sys
import os
from PyQt5.QtGui import QIcon

# Ensure the app directory is in path
sys.path.insert(0, os.path.dirname(__file__))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from gui import MainWindow

def main():
    # Enable HiDPI support
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("EZDL")
    app.setApplicationVersion("2.0.0")
    icon_path = os.path.join(os.path.dirname(__file__), "icon512.png")
    app.setWindowIcon(QIcon(icon_path))
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
