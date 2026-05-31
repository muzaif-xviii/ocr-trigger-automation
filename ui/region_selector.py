"""
region_selector.py
Full-screen transparent overlay allowing the user to drag-select a capture region.
Returns [left, top, width, height] via the RegionSelector.region_selected signal.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget

logger = logging.getLogger(__name__)


class RegionSelector(QWidget):
    """
    Fullscreen transparent overlay for click-drag region selection.

    Signals
    -------
    region_selected(list[int]) — emitted when the user releases the mouse.
        Format: [left, top, width, height] in screen coordinates.
    cancelled — emitted if the user presses Escape or makes too small a selection.
    """

    region_selected = Signal(list)
    cancelled = Signal()

    _MIN_SIZE = 20  # minimum px for width/height to accept the selection

    def __init__(self) -> None:
        super().__init__()
        self._start: QPoint | None = None
        self._end: QPoint | None = None
        self._selecting = False
        self._setup_window()

    # ------------------------------------------------------------------ #
    # Setup                                                                #
    # ------------------------------------------------------------------ #

    def _setup_window(self) -> None:
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setCursor(QCursor(Qt.CursorShape.CrossCursor))

        # Span all virtual screens
        screen_geometry = QApplication.primaryScreen().virtualGeometry()
        self.setGeometry(screen_geometry)
        self.setMouseTracking(True)

    # ------------------------------------------------------------------ #
    # Events                                                               #
    # ------------------------------------------------------------------ #

    def showEvent(self, event) -> None:  # noqa: N802
        self.grabKeyboard()
        super().showEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.releaseKeyboard()
            self.close()
            self.cancelled.emit()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._start = event.globalPosition().toPoint()
            self._end = self._start
            self._selecting = True
            self.update()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._selecting:
            self._end = event.globalPosition().toPoint()
            self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._selecting:
            self._selecting = False
            self._end = event.globalPosition().toPoint()
            self.releaseKeyboard()
            self.close()
            self._emit_region()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)

        # Dark semi-transparent overlay
        painter.fillRect(self.rect(), QColor(0, 0, 0, 100))

        if self._start and self._end:
            rect = QRect(self._start, self._end).normalized()

            # Clear (transparent) inside selection
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(rect, QColor(0, 0, 0, 255))

            # Draw border
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            pen = QPen(QColor(124, 58, 237), 2, Qt.PenStyle.SolidLine)
            painter.setPen(pen)
            painter.drawRect(rect)

            # Cyan corner accents
            accent_pen = QPen(QColor(6, 182, 212), 3)
            painter.setPen(accent_pen)
            corner_len = 12
            tl = rect.topLeft()
            tr = rect.topRight()
            bl = rect.bottomLeft()
            br = rect.bottomRight()
            for px, py, dx, dy in [
                (tl.x(), tl.y(), 1, 1),
                (tr.x(), tr.y(), -1, 1),
                (bl.x(), bl.y(), 1, -1),
                (br.x(), br.y(), -1, -1),
            ]:
                painter.drawLine(px, py, px + dx * corner_len, py)
                painter.drawLine(px, py, px, py + dy * corner_len)

            # Size label
            w, h = rect.width(), rect.height()
            if w > 60 and h > 24:
                painter.setPen(QColor(241, 245, 249))
                painter.drawText(rect.adjusted(6, 4, 0, 0), f"{w} × {h}")

        painter.end()

    # ------------------------------------------------------------------ #
    # Emit                                                                 #
    # ------------------------------------------------------------------ #

    def _emit_region(self) -> None:
        if not (self._start and self._end):
            self.cancelled.emit()
            return

        rect = QRect(self._start, self._end).normalized()
        if rect.width() < self._MIN_SIZE or rect.height() < self._MIN_SIZE:
            logger.debug("Selection too small: %dx%d", rect.width(), rect.height())
            self.cancelled.emit()
            return

        region = [rect.left(), rect.top(), rect.width(), rect.height()]
        logger.info("Region selected: %s", region)
        self.region_selected.emit(region)
