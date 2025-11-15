#!/usr/bin/env python3
"""Gen3 AWE Control GUI Application"""

import sys
import logging
import ctypes
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from main_window import MainWindow

# Suppress library noise - only show critical errors
logging.getLogger('pymodbus').setLevel(logging.CRITICAL)
logging.getLogger('nidaqmx').setLevel(logging.WARNING)


def main():
    # Set Windows App ID (makes taskbar icon work correctly on Windows)
    if sys.platform == 'win32':
        myappid = 'terraformindustries.gen3awe.control.1.0'
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    
    app = QApplication(sys.argv)
    
    # Set app icon
    icon_path = Path(__file__).parent.parent.parent / "assets" / "favicon.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

