import sys
from PyQt6.QtWidgets import QApplication
from ui.main_window import MainWindow
from ui.styles import GLOBAL_STYLESHEET

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(GLOBAL_STYLESHEET)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
