"""
ocr_engine.py
Wraps pytesseract to extract text with per-word confidence scores.
Designed to run in the background OCR thread.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pytesseract

logger = logging.getLogger(__name__)

# Tesseract config: raw page segmentation, no OSD
_TESSERACT_CONFIG = "--psm 6 --oem 3"


@dataclass
class OcrWord:
    text: str
    confidence: float
    left: int
    top: int
    width: int
    height: int


@dataclass
class OcrResult:
    raw_text: str = ""
    words: list[OcrWord] = field(default_factory=list)
    avg_confidence: float = 0.0
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.error is None and bool(self.raw_text.strip())


class OcrEngine:
    """
    Extracts text from pre-processed numpy images using pytesseract.

    Usage
    -----
    engine = OcrEngine(confidence_threshold=60)
    result = engine.run(preprocessed_image)
    """

    def __init__(
        self,
        confidence_threshold: int = 60,
        tesseract_cmd: Optional[str] = None,
    ) -> None:
        self.confidence_threshold = confidence_threshold
        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        self._verify_tesseract()

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    def _verify_tesseract(self) -> None:
        """Log a warning if Tesseract is not reachable."""
        try:
            pytesseract.get_tesseract_version()
        except Exception as exc:
            logger.warning(
                "Tesseract not found or not accessible: %s\n"
                "Install from https://github.com/UB-Mannheim/tesseract/wiki",
                exc,
            )

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def run(self, image: np.ndarray) -> OcrResult:
        """
        Run OCR on a pre-processed (binary greyscale) numpy array.

        Returns an OcrResult with filtered words above the confidence threshold.
        """
        if image is None or image.size == 0:
            return OcrResult(error="Empty image provided")

        try:
            data = pytesseract.image_to_data(
                image,
                config=_TESSERACT_CONFIG,
                output_type=pytesseract.Output.DICT,
            )
        except pytesseract.TesseractNotFoundError:
            return OcrResult(error="Tesseract not installed or not in PATH")
        except Exception as exc:
            logger.error("OCR failed: %s", exc)
            return OcrResult(error=str(exc))

        words: list[OcrWord] = []
        confidences: list[float] = []

        n_boxes = len(data["level"])
        for i in range(n_boxes):
            text = str(data["text"][i]).strip()
            if not text:
                continue
            try:
                conf = float(data["conf"][i])
            except (ValueError, TypeError):
                conf = -1.0

            if conf < self.confidence_threshold:
                continue

            words.append(
                OcrWord(
                    text=text,
                    confidence=conf,
                    left=data["left"][i],
                    top=data["top"][i],
                    width=data["width"][i],
                    height=data["height"][i],
                )
            )
            confidences.append(conf)

        raw_text = " ".join(w.text for w in words)
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0

        return OcrResult(
            raw_text=raw_text,
            words=words,
            avg_confidence=round(avg_conf, 1),
        )

    def set_confidence_threshold(self, threshold: int) -> None:
        self.confidence_threshold = max(0, min(100, threshold))

    def set_tesseract_cmd(self, path: str) -> None:
        pytesseract.pytesseract.tesseract_cmd = path
        self._verify_tesseract()
