#!/usr/bin/env python3
"""Gen3 AWE Control GUI Application"""

import sys
import logging
from PySide6.QtWidgets import QApplication
from main_window import MainWindow

# Suppress library noise - only show critical errors
logging.getLogger('pymodbus').setLevel(logging.CRITICAL)
logging.getLogger('nidaqmx').setLevel(logging.WARNING)


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

