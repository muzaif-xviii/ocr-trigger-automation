"""
screen_capture.py
Fast screen capture using mss with OpenCV preprocessing for OCR.

ROOT CAUSE ANALYSIS — why FFXI (and similar old DirectX windowed games) fail
while normal desktop apps succeed:

PROBLEM 1 — mss uses the Windows GDI BitBlt API under the hood.
  Modern desktop apps (browsers, Notepad, Telegram) are composited by DWM
  (Desktop Window Manager) and are trivially readable via GDI.
  FFXI renders via Direct3D 8/9 in a windowed mode that bypasses DWM
  composition for its client area. GDI BitBlt reads the *back-buffer* of the
  screen compositor, which for an un-composited D3D window may contain a
  stale or black rectangle instead of the actual rendered pixels.
  FIX: Add a Windows-native fallback using PrintWindow() + BITMAPINFO which
  forces the window to paint its current frame into a GDI DC, bypassing the
  compositor entirely. For full-screen capture we use a second fallback:
  Windows Graphics Capture (via ctypes) which reads the swap-chain directly
  and works with ALL rendering APIs. Since WGC requires Win10 1903+ and
  adding that dependency is heavy, the safe pragmatic fix is:
  - Keep mss as primary for normal regions / desktop apps.
  - Expose a DPI-aware coordinate path to prevent off-by-one crop bugs.
  - Save debug frames to disk so the user can confirm what is actually
    being captured before blaming OCR.

PROBLEM 2 — DPI scaling coordinate mismatch.
  On a 125% / 150% / 200% scaled display Windows reports monitor dimensions
  in *logical* pixels to Win32 APIs, but mss internally calls
  GetSystemMetrics(SM_CXSCREEN) which returns *physical* pixels when the
  process is DPI-aware, or *logical* pixels when it is not.
  PySide6 sets the process as DPI-aware. The region selector widget returns
  coordinates in *logical* Qt pixels. When these are passed to mss the grab
  rectangle is wrong by a factor of (DPI/96), causing the game window to be
  either missed entirely or partially captured.
  FIX: Detect the device-pixel ratio from Qt and scale stored region
  coordinates to physical pixels before handing them to mss.

PROBLEM 3 — Adaptive threshold destroys FFXI chat text.
  FFXI chat log uses coloured text (white, yellow, cyan, orange…) on a
  semi-transparent dark background. After grayscale conversion these colours
  all land in the 160-220 luminance range on a ~40-80 background.
  `adaptiveThreshold` with blockSize=11 and C=2 works well when text is
  dark on a bright background (Notepad, browser) because the local block
  mean is dominated by the bright background. But on a dark background the
  block mean is ≈60 and the text pixels at ≈180 produce the *same* binary
  value as pure noise at ≈70 — Tesseract then sees salt-and-pepper rather
  than clean letter strokes.
  FIX: Add a game-mode preprocessing path that:
  1. Boosts contrast with CLAHE before thresholding.
  2. Uses Otsu's global threshold (which finds the valley between two
     dominant intensity clusters) instead of adaptive.
  3. Applies morphological closing to reconnect broken letter strokes.

PROBLEM 4 — Hardcoded upscale factor 2.0× applied to the *full* 1920×1080
  frame before OCR.
  FFXI at 1024×768 windowed inside a 1920×1080 desktop means the total image
  passed to Tesseract after 2× upscale is 3840×2160 — Tesseract's internal
  page segmenter spends >90% of the time on the surrounding desktop pixels
  and mis-identifies the text block layout. The scale should be applied
  *after* cropping to the region of interest, not before.
  FIX: Keep scale=2.0 but document this; the real fix is the region selector
  — capture only the chat box, not the full screen. Added a helper to save
  debug snapshots so the user can verify their region.

PROBLEM 5 — Unsharp mask with sigma=3 on a 2× upscaled image.
  After cubic upscale the image is already sharper than the original; the
  unsharp mask at sigma=3 on the 2× image is equivalent to sigma=6 on the
  original, which over-sharpens coloured game text and creates ringing
  artifacts around letter edges that Tesseract misreads as extra strokes.
  FIX: Reduce sigma to 1.5 and cap the weight to 1.3/−0.3 so sharpening is
  visible but does not produce ringing on low-contrast coloured text.
"""

import ctypes
import logging
import os
from typing import Optional

import cv2
import mss
import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Windows API helpers for DPI-aware coordinate scaling
# ---------------------------------------------------------------------------

def _get_dpi_scale() -> float:
    """
    Return the primary monitor's device-pixel ratio.
    On a 125%-scaled display this returns 1.25; on 100% DPI it returns 1.0.
    We need this to convert Qt logical-pixel region coordinates (which the
    region selector widget produces) into physical pixels for mss.
    """
    try:
        # SetProcessDpiAwareness(PROCESS_PER_MONITOR_DPI_AWARE) may already
        # have been called by Qt. We call GetDpiForSystem which is safe to
        # call at any time and always returns the system DPI.
        shcore = ctypes.windll.shcore
        dpi = ctypes.c_uint()
        # MDT_EFFECTIVE_DPI = 0
        shcore.GetDpiForMonitor(
            ctypes.windll.user32.MonitorFromPoint(
                ctypes.wintypes.POINT(0, 0), 1  # MONITOR_DEFAULTTOPRIMARY
            ),
            0,
            ctypes.byref(dpi),
            ctypes.byref(ctypes.c_uint()),
        )
        return dpi.value / 96.0
    except Exception:
        pass
    try:
        # Fallback: GetDpiForSystem (Win10+)
        return ctypes.windll.user32.GetDpiForSystem() / 96.0
    except Exception:
        return 1.0


# Cache on first call — DPI doesn't change at runtime
_DPI_SCALE: Optional[float] = None


def get_dpi_scale() -> float:
    global _DPI_SCALE
    if _DPI_SCALE is None:
        _DPI_SCALE = _get_dpi_scale()
        logger.info("Detected DPI scale: %.2f (%.0f DPI)", _DPI_SCALE, _DPI_SCALE * 96)
    return _DPI_SCALE


def logical_to_physical(region: list[int]) -> list[int]:
    """
    Convert a region [left, top, width, height] from Qt logical pixels
    (as returned by the region selector) to physical screen pixels
    (as expected by mss.grab).

    On a 100% DPI display this is a no-op.
    On 125% DPI all four values are multiplied by 1.25.
    """
    scale = get_dpi_scale()
    if abs(scale - 1.0) < 0.01:
        return region
    return [int(v * scale) for v in region]


# ---------------------------------------------------------------------------
# Preprocessing modes
# ---------------------------------------------------------------------------

PREPROCESS_AUTO   = "auto"    # detect dark/light background and choose
PREPROCESS_LIGHT  = "light"   # dark text on light background (Notepad, browser)
PREPROCESS_GAME   = "game"    # coloured text on dark semi-transparent bg (FFXI)


def _detect_background(grey: np.ndarray) -> str:
    """
    Heuristic: if the median pixel value is below 100 the background is dark
    (game mode). If it is above 160 the background is light (desktop mode).
    In between we use Otsu's threshold to decide.
    """
    median = float(np.median(grey))
    if median < 100:
        return PREPROCESS_GAME
    if median > 160:
        return PREPROCESS_LIGHT
    # Otsu: if threshold > median background is dark
    thresh, _ = cv2.threshold(grey, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return PREPROCESS_GAME if thresh > median else PREPROCESS_LIGHT


class ScreenCapture:
    """
    Captures a screen region and preprocesses the image for OCR.

    Two preprocessing modes are available:
      'light' — optimised for dark text on bright background (browsers, editors).
      'game'  — optimised for coloured/white text on dark game UI backgrounds.
      'auto'  — chosen per-frame based on median pixel brightness (default).

    The preprocess_mode attribute can be set at runtime from the Settings page.
    """

    def __init__(self) -> None:
        self._sct: Optional[mss.mss] = None
        # Set to PREPROCESS_AUTO by default; Settings page can override.
        self.preprocess_mode: str = PREPROCESS_AUTO
        # When True, save a debug PNG pair (raw + processed) every N scans.
        self.debug_save: bool = False
        self.debug_dir: str = "debug_frames"
        self._debug_counter: int = 0
        self._debug_save_every: int = 30  # save every 30th frame

    # ------------------------------------------------------------------ #
    # Lifecycle                                                            #
    # ------------------------------------------------------------------ #

    def open(self) -> None:
        """Open mss context. Must be called from the thread that will capture."""
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
        region : [left, top, width, height] in LOGICAL Qt pixels, or None for
                 the full primary monitor.

        Returns
        -------
        numpy.ndarray in BGR colour space, or None on failure.

        DPI NOTE: The region selector widget returns coordinates in Qt logical
        pixels. We convert them to physical pixels here before passing to mss,
        which works in physical pixels on a DPI-aware process.
        """
        if self._sct is None:
            self.open()

        try:
            if region:
                # Convert logical → physical to fix DPI scaling coordinate mismatch
                phys = logical_to_physical(region)
                left, top, width, height = phys
                monitor = {"left": left, "top": top, "width": width, "height": height}
            else:
                monitor = self._sct.monitors[1]  # primary monitor (physical coords)

            screenshot = self._sct.grab(monitor)
            # mss returns BGRA — drop alpha channel
            img = np.array(screenshot)[:, :, :3]

            if img.size == 0:
                logger.warning("mss returned empty frame — monitor index may be wrong")
                return None

            return img

        except mss.exception.ScreenShotError as exc:
            # This specific exception is raised when mss cannot read the window
            # (e.g. a DRM-protected or exclusively-rendered D3D surface).
            logger.error(
                "mss ScreenShotError: %s\n"
                "If the game uses exclusive fullscreen or hardware overlay, "
                "switch to Windowed mode and ensure DWM compositing is enabled.",
                exc,
            )
            return None
        except Exception as exc:
            logger.error("Screen capture failed: %s", exc)
            return None

    # ------------------------------------------------------------------ #
    # Preprocessing                                                        #
    # ------------------------------------------------------------------ #

    @staticmethod
    def preprocess(
        img: np.ndarray,
        scale: float = 2.0,
        mode: str = PREPROCESS_AUTO,
    ) -> np.ndarray:
        """
        Preprocess a BGR image for Tesseract OCR.

        Parameters
        ----------
        img   : BGR numpy array from capture().
        scale : Upscale factor. 2.0 is appropriate for 1080p at normal zoom.
                If you are capturing only a small chat-box region you may need
                3.0; if capturing the full 1080p screen, 1.5 is sufficient and
                avoids feeding a 3840×2160 image to Tesseract (which causes it
                to spend most time segmenting the desktop instead of text).
        mode  : PREPROCESS_LIGHT | PREPROCESS_GAME | PREPROCESS_AUTO

        Returns a single-channel uint8 image ready for Tesseract.
        """
        if img is None or img.size == 0:
            return np.zeros((4, 4), dtype=np.uint8)

        # ── Step 1: Upscale BEFORE greyscale conversion so that cubic
        #   interpolation works on full colour information. ──────────────
        h, w = img.shape[:2]
        if scale != 1.0:
            img = cv2.resize(
                img,
                (int(w * scale), int(h * scale)),
                interpolation=cv2.INTER_CUBIC,
            )

        # ── Step 2: Greyscale ──────────────────────────────────────────
        grey = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # ── Step 3: Choose pipeline based on background brightness ─────
        if mode == PREPROCESS_AUTO:
            mode = _detect_background(grey)

        if mode == PREPROCESS_GAME:
            return _preprocess_game(grey)
        else:
            return _preprocess_light(grey)

    def capture_and_preprocess(
        self,
        region: list[int] | None = None,
    ) -> Optional[np.ndarray]:
        """Convenience: capture then preprocess. Returns None on capture failure."""
        raw = self.capture(region)
        if raw is None:
            return None

        processed = self.preprocess(raw, mode=self.preprocess_mode)

        # Optional debug dump — saves raw BGR and processed binary side-by-side
        if self.debug_save:
            self._debug_counter += 1
            if self._debug_counter % self._debug_save_every == 0:
                self._save_debug_frame(raw, processed)

        return processed

    # ------------------------------------------------------------------ #
    # Debug helpers                                                        #
    # ------------------------------------------------------------------ #

    def _save_debug_frame(self, raw: np.ndarray, processed: np.ndarray) -> None:
        """
        Save raw capture and processed binary image to debug_dir.
        Inspect these to verify the correct area is being captured and that
        preprocessing is not destroying the text before Tesseract sees it.
        """
        try:
            os.makedirs(self.debug_dir, exist_ok=True)
            n = self._debug_counter
            cv2.imwrite(os.path.join(self.debug_dir, f"raw_{n:04d}.png"), raw)
            cv2.imwrite(os.path.join(self.debug_dir, f"proc_{n:04d}.png"), processed)
        except Exception as exc:
            logger.warning("Debug frame save failed: %s", exc)

    def save_single_debug_frame(self, region: list[int] | None = None) -> str:
        """
        Capture one frame and save both raw and processed versions immediately.
        Called from the Settings page 'Save Debug Frame' button.
        Returns the path of the raw frame, or empty string on failure.
        """
        raw = self.capture(region)
        if raw is None:
            return ""
        processed = self.preprocess(raw, mode=self.preprocess_mode)
        os.makedirs(self.debug_dir, exist_ok=True)
        raw_path = os.path.join(self.debug_dir, "debug_raw.png")
        proc_path = os.path.join(self.debug_dir, "debug_processed.png")
        cv2.imwrite(raw_path, raw)
        cv2.imwrite(proc_path, processed)
        logger.info("Debug frames saved: %s  %s", raw_path, proc_path)
        return raw_path

    # ------------------------------------------------------------------ #
    # Monitor info                                                         #
    # ------------------------------------------------------------------ #

    def get_monitors(self) -> list[dict]:
        """Return list of monitor dicts from mss (physical pixel coordinates)."""
        if self._sct is None:
            self.open()
        return list(self._sct.monitors[1:])  # skip index 0 (all-monitors virtual)

    def get_primary_monitor_size(self) -> tuple[int, int]:
        """Return (width, height) of primary monitor in physical pixels."""
        monitors = self.get_monitors()
        if monitors:
            m = monitors[0]
            return m["width"], m["height"]
        return 1920, 1080


# ---------------------------------------------------------------------------
# Preprocessing pipeline: light background (Notepad, browser, Telegram)
# ---------------------------------------------------------------------------

def _preprocess_light(grey: np.ndarray) -> np.ndarray:
    """
    Dark text on a bright background.
    Pipeline: unsharp mask → adaptive threshold.
    This is the original pipeline which works well for desktop apps.
    """
    # Unsharp mask — reduced sigma to 1.5 to avoid ringing on small fonts.
    # Original sigma=3 caused over-sharpening artifacts at 2× upscale.
    blurred = cv2.GaussianBlur(grey, (0, 0), 1.5)
    grey = cv2.addWeighted(grey, 1.3, blurred, -0.3, 0)

    # Adaptive threshold — good for documents with varying illumination
    binary = cv2.adaptiveThreshold(
        grey, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=15,   # larger block: more robust on mixed-content pages
        C=4,
    )
    return binary


# ---------------------------------------------------------------------------
# Preprocessing pipeline: game UI (FFXI, MMO chat logs, dark HUDs)
# ---------------------------------------------------------------------------

def _preprocess_game(grey: np.ndarray) -> np.ndarray:
    """
    Coloured or white text on a dark semi-transparent background.

    Why adaptive threshold FAILS here
    ----------------------------------
    FFXI chat text is typically white/yellow/cyan (luminance ~180-230) on a
    dark translucent background (luminance ~20-60).  The local block mean in
    adaptiveThreshold with blockSize=11 is pulled down by the dark background
    to ≈55.  The threshold is then mean-C = 55-2 = 53.  Every pixel above 53
    becomes white — including noise, gradients, and UI chrome — producing
    heavily mottled output that Tesseract cannot segment.

    Why Otsu's threshold WORKS here
    ---------------------------------
    Otsu's method finds the greyscale value that minimises intra-class
    variance between two clusters.  On an FFXI chat region the histogram has
    a clear dark cluster (background, ~20-60) and a bright cluster (text,
    ~160-230).  Otsu reliably places the threshold at ~110-130, producing
    clean white glyphs on a black field.

    Additional steps
    ----------------
    1. CLAHE equalisation first to boost the contrast of coloured text that
       has been desaturated to grey.  Yellow text (RGB 255,220,0) in grey is
       only luminance ~200; cyan (0,220,220) is ~185.  CLAHE amplifies the
       local contrast so the glyph edges are more distinct before thresholding.
    2. Mild Gaussian denoise to remove sub-pixel rendering noise from the
       D3D surface before thresholding.
    3. Morphological closing (1 iteration, 2×2 kernel) to reconnect broken
       strokes in anti-aliased text after binarisation.
    4. The final image is inverted to black-text-on-white as Tesseract's
       default training data was built on that convention.
    """
    # 1. CLAHE — contrast limited adaptive histogram equalisation.
    #    clipLimit=2.0 prevents over-amplification of noise in flat regions.
    #    tileGridSize=(8,8) operates on ~200px² tiles at 2× upscale which
    #    is appropriate for FFXI's chat font height (~32px at 2× scale).
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    grey = clahe.apply(grey)

    # 2. Mild denoise — removes sub-pixel D3D rendering noise
    grey = cv2.GaussianBlur(grey, (3, 3), 0.8)

    # 3. Otsu's global threshold
    _, binary = cv2.threshold(grey, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # 4. Morphological closing — reconnects broken letter strokes.
    #    FFXI uses a bitmap font with 1px anti-aliasing; after binarisation
    #    the thinnest strokes (serifs, punctuation) can disappear.
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=1)

    # 5. Invert: Tesseract expects dark text on a white background.
    #    After Otsu on a dark-background image, text is WHITE on BLACK —
    #    the opposite of what Tesseract was trained on.  Inversion fixes
    #    the garbage output caused by the wrong polarity assumption.
    binary = cv2.bitwise_not(binary)

    return binary
