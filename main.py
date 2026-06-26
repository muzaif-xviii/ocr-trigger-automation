"""
main.py
Entry point for Screen Trigger Macro.
Configures logging, creates the QApplication, and launches the main window.

PATH NOTE — frozen EXE
-----------------------
When PyInstaller bundles this file, __file__ resolves to a path inside the
temporary extraction directory (_MEIXXXXXX).  Any directory derived from
__file__ is therefore temporary and will be deleted when the process exits.

All persistent paths (logs, config, profiles) must be anchored to
Path(sys.executable).parent — the directory containing the actual EXE.

_resolve_base_dir() from config_manager handles this consistently.  We
import it here so that the log file is created in the correct location
before ConfigManager even runs, ensuring that the path-diagnostic log
lines emitted by ConfigManager.__init__ are captured to disk.
"""

import logging
import sys
from pathlib import Path

# Ensure the project root is importable when running from source.
# When frozen, sys.path is managed by PyInstaller and this is a no-op.
_SOURCE_ROOT = Path(__file__).resolve().parent
if str(_SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(_SOURCE_ROOT))

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

# Import the base-dir resolver before anything else so logging lands in the
# right place whether we are frozen or running from source.
from core.config_manager import _resolve_base_dir
from ui.main_window import MainWindow


# ── Logging setup ──────────────────────────────────────────────────────── #

def _setup_logging() -> None:
    """
    Configure root logger with a stdout stream handler and a rotating file
    handler.  The log directory is resolved using the same _resolve_base_dir()
    function that ConfigManager uses, ensuring log files land next to the EXE
    when frozen and next to main.py when running from source.
    """
    base = _resolve_base_dir()
    log_dir = base / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "stm.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )
    logging.getLogger("PIL").setLevel(logging.WARNING)
    logging.getLogger("pytesseract").setLevel(logging.WARNING)

    # Emit the resolved log path immediately so it appears at the very top
    # of every log file and on stdout.
    logging.getLogger(__name__).info("Log file: %s", log_file)


# ── Main ───────────────────────────────────────────────────────────────── #

def main() -> None:
    _setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Starting Screen Trigger Macro")
    logger.info("Python  : %s", sys.version.split()[0])
    logger.info("Frozen  : %s", getattr(sys, "frozen", False))

    QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("Screen Trigger Macro")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("STM")
    app.setQuitOnLastWindowClosed(False)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
