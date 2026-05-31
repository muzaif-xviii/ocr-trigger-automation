"""
main.py
Entry point for Screen Trigger Macro.
Configures logging, creates the QApplication, and launches the main window.
"""

import logging
import sys
from pathlib import Path

# Ensure project root is importable when run directly
ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow

# ── Logging setup ──────────────────────────────────────────────────────── #

def _setup_logging() -> None:
    log_dir = ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "stm.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )
    # Quieten noisy third-party loggers
    logging.getLogger("PIL").setLevel(logging.WARNING)
    logging.getLogger("pytesseract").setLevel(logging.WARNING)


# ── Main ───────────────────────────────────────────────────────────────── #

def main() -> None:
    _setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Starting Screen Trigger Macro")

    # High-DPI support
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("Screen Trigger Macro")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("STM")

    # Prevent app quitting when main window is hidden to tray
    app.setQuitOnLastWindowClosed(False)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
