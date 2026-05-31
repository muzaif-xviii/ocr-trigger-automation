"""
screen_capture.py
Fast screen capture using mss with OpenCV preprocessing for OCR.
Grayscale, adaptive threshold, and unsharp masking to maximize Tesseract accuracy.
"""

import logging
from typing import Optional

import cv2
import mss
import numpy as np

logger = logging.getLogger(__name__)


class ScreenCapture:
    """Captures a screen region and preprocesses the image for OCR."""

    def __init__(self) -> None:
        # mss instance is not thread-safe — each thread should create its own.
        self._sct: Optional[mss.mss] = None

    # ------------------------------------------------------------------ #
    # Lifecycle                                                            #
    # ------------------------------------------------------------------ #

    def open(self) -> None:
        """Open mss context. Call from the thread that will do capturing."""
        if self._sct is None:
            self._sct = mss.mss()

    def close(self) -> None:
        """Release mss context."""
        if self._sct is not None:
            self._sct.close()
            self._sct = None

    # ------------------------------------------------------------------ #
    # Capture                                                              #
    # ------------------------------------------------------------------ #

    def capture(self, region: list[int] | None = None) -> Optional[np.ndarray]:
        """
        Capture a screen region.

        Parameters
        ----------
        region : [left, top, width, height] or None for full primary monitor.

        Returns
        -------
        numpy.ndarray in BGR colour space, or None on failure.
        """
        if self._sct is None:
            self.open()

        try:
            if region:
                left, top, width, height = region
                monitor = {"left": left, "top": top, "width": width, "height": height}
            else:
                monitor = self._sct.monitors[1]  # primary monitor

            screenshot = self._sct.grab(monitor)
            # mss returns BGRA — drop alpha channel
            img = np.array(screenshot)[:, :, :3]
            return img
        except Exception as exc:
            logger.error("Screen capture failed: %s", exc)
            return None

    # ------------------------------------------------------------------ #
    # Preprocessing                                                        #
    # ------------------------------------------------------------------ #

    @staticmethod
    def preprocess(img: np.ndarray, scale: float = 2.0) -> np.ndarray:
        """
        Preprocess a BGR image for Tesseract OCR.

        Steps:
        1. Upscale (Tesseract performs better on larger text)
        2. Convert to greyscale
        3. Unsharp mask for sharpening
        4. Adaptive threshold for binarisation

        Returns a single-channel binary image.
        """
        # 1. Upscale
        h, w = img.shape[:2]
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)

        # 2. Greyscale
        grey = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # 3. Unsharp mask (sharpen)
        blurred = cv2.GaussianBlur(grey, (0, 0), 3)
        grey = cv2.addWeighted(grey, 1.5, blurred, -0.5, 0)

        # 4. Adaptive threshold — handles varying background brightness
        binary = cv2.adaptiveThreshold(
            grey, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            blockSize=11,
            C=2,
        )

        return binary

    def capture_and_preprocess(self, region: list[int] | None = None) -> Optional[np.ndarray]:
        """Convenience: capture then preprocess in one call."""
        raw = self.capture(region)
        if raw is None:
            return None
        return self.preprocess(raw)

    # ------------------------------------------------------------------ #
    # Monitor info                                                         #
    # ------------------------------------------------------------------ #

    def get_monitors(self) -> list[dict]:
        """Return list of monitor dicts from mss."""
        if self._sct is None:
            self.open()
        return list(self._sct.monitors[1:])  # skip index 0 (all-monitors)

    def get_primary_monitor_size(self) -> tuple[int, int]:
        """Return (width, height) of primary monitor."""
        monitors = self.get_monitors()
        if monitors:
            m = monitors[0]
            return m["width"], m["height"]
        return 1920, 1080
