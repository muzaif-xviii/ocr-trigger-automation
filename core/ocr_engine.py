"""
ocr_engine.py
Wraps pytesseract to extract text with per-word confidence scores.

ROOT CAUSE — why PSM 6 fails on FFXI chat logs
------------------------------------------------
--psm 6 tells Tesseract to "assume a single uniform block of text".
This is correct for a full-page document scan.  For an FFXI chat window it
is wrong for two reasons:

1. The chat log is a narrow vertical strip with short lines of variable
   length.  PSM 6 expects a wide rectangular block; it will try to find
   columns and rows across the full image and will mis-segment the layout,
   treating two short chat lines as one broken sentence or as noise.

2. FFXI renders its chat with a monospaced bitmap font at small point sizes
   (~11-13pt at 1× game resolution).  After 2× upscale the glyphs are
   22-26px tall.  PSM 6 expects body-text-sized characters; at this size it
   applies heuristics designed for 12pt+ proportional fonts that generate
   incorrect baseline and x-height estimates, leading to garbage output.

FIX: Use --psm 11 (sparse text) for full-screen or large-region scans.
PSM 11 does not assume a reading order or a uniform block; it finds text
anywhere in the image.  This is the correct mode for an HUD/game overlay
where text appears in scattered UI panels.

SECONDARY FIX: Add --psm 6 as an option for targeted chat-box crops (when
the user has used the region selector to isolate the chat area).  Expose
the PSM setting in the Settings page so the user can tune it.

CONFIDENCE THRESHOLD ISSUE
---------------------------
The default threshold of 60 silently drops all words below confidence 60.
FFXI's bitmap font after preprocessing typically scores 35-65 per word —
so with threshold=60 roughly half the chat words are discarded before the
trigger engine ever sees them.  The default should be 30 for game use.
The threshold is still user-configurable so desktop-app users can raise it.

ADDITIONAL FIX: expose image_to_string as an alternative to image_to_data
for simple all-or-nothing text extraction; it has lower per-call overhead
and is sufficient for trigger matching (which only needs the text, not
bounding boxes).
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pytesseract

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tesseract config strings
# ---------------------------------------------------------------------------

# PSM 11 — sparse text, no assumed layout.
# Best for: game overlays, HUDs, full-screen scans with scattered UI text.
# Use this when scanning the full screen or a large region.
TESS_CONFIG_SPARSE = "--psm 11 --oem 3"

# PSM 6 — uniform block of text.
# Best for: a tightly-cropped chat log region, document pages.
# Use this when the user has region-selected specifically the chat box.
TESS_CONFIG_BLOCK = "--psm 6 --oem 3"

# PSM 7 — single text line.
# Best for: a single-line title bar or status indicator.
TESS_CONFIG_LINE = "--psm 7 --oem 3"

# Default: sparse is safer for mixed-content / full-screen captures
_DEFAULT_CONFIG = TESS_CONFIG_SPARSE


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

    Key tunables
    ------------
    confidence_threshold : int
        Words with Tesseract confidence below this value are discarded.
        Default: 30.  Desktop apps can raise to 60; game OCR should stay
        at 25-40 because game fonts score lower than document fonts.

    tesseract_config : str
        Full Tesseract CLI flags string.  Use TESS_CONFIG_SPARSE for
        full-screen/large-region game capture, TESS_CONFIG_BLOCK for a
        tightly-cropped chat area.  Exposed in Settings.
    """

    def __init__(
        self,
        confidence_threshold: int = 30,
        tesseract_cmd: Optional[str] = None,
        tesseract_config: str = _DEFAULT_CONFIG,
    ) -> None:
        # Lowered default from 60 → 30.  FFXI bitmap font scores 35-65;
        # threshold=60 silently drops most chat words before trigger matching.
        self.confidence_threshold = confidence_threshold
        self.tesseract_config = tesseract_config

        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

        self._verify_tesseract()

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    def _verify_tesseract(self) -> None:
        """Log a warning if Tesseract is not reachable."""
        try:
            version = pytesseract.get_tesseract_version()
            logger.info("Tesseract version: %s", version)
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

        Returns an OcrResult with filtered words above confidence_threshold.
        """
        if image is None or image.size == 0:
            return OcrResult(error="Empty image provided")

        try:
            data = pytesseract.image_to_data(
                image,
                config=self.tesseract_config,
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

            # conf == -1 means Tesseract could not assign a confidence
            # (common for non-text blocks in PSM 11).  Treat as 0.
            if conf < 0:
                conf = 0.0

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

        # Log at DEBUG so the scan loop logs are not flooded
        logger.debug(
            "OCR: %d words, avg_conf=%.1f, threshold=%d, first80=%r",
            len(words),
            avg_conf,
            self.confidence_threshold,
            raw_text[:80],
        )

        return OcrResult(
            raw_text=raw_text,
            words=words,
            avg_confidence=round(avg_conf, 1),
        )

    def run_simple(self, image: np.ndarray) -> str:
        """
        Simpler alternative using image_to_string.
        Lower overhead; returns raw string with no confidence filtering.
        Useful for debugging: if run_simple returns correct text but run()
        returns nothing, the confidence threshold is too high.
        """
        if image is None or image.size == 0:
            return ""
        try:
            return pytesseract.image_to_string(image, config=self.tesseract_config)
        except Exception as exc:
            logger.error("OCR (simple) failed: %s", exc)
            return ""

    def set_confidence_threshold(self, threshold: int) -> None:
        self.confidence_threshold = max(0, min(100, threshold))
        logger.info("OCR confidence threshold set to %d", self.confidence_threshold)

    def set_tesseract_cmd(self, path: str) -> None:
        pytesseract.pytesseract.tesseract_cmd = path
        self._verify_tesseract()

    def set_tesseract_config(self, config: str) -> None:
        """Override the full Tesseract CLI flags at runtime."""
        self.tesseract_config = config
        logger.info("Tesseract config set to: %s", config)
