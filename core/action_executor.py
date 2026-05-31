"""
action_executor.py
Executes keyboard actions (hotkeys, sequences, delays) via the keyboard library.
Runs actions in a dedicated thread to avoid blocking the OCR loop.
"""

import logging
import time
from queue import Empty, Queue
from threading import Event, Thread
from typing import Any

import keyboard

logger = logging.getLogger(__name__)


class ActionExecutor:
    """
    Thread-safe action queue that executes keyboard macros.

    Supports two action types:
    - hotkey: press a combination like alt+1, ctrl+shift+f2
    - sequence: list of steps [{type:hotkey|delay, keys:[...], ms:N}]

    Usage
    -----
    executor = ActionExecutor()
    executor.start()
    executor.execute(action_dict)
    executor.stop()
    """

    def __init__(self) -> None:
        self._queue: Queue[dict[str, Any]] = Queue()
        self._stop_event = Event()
        self._thread: Thread | None = None
        self.enabled: bool = True

    # ------------------------------------------------------------------ #
    # Lifecycle                                                            #
    # ------------------------------------------------------------------ #

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = Thread(target=self._worker, name="ActionExecutor", daemon=True)
        self._thread.start()
        logger.debug("ActionExecutor started")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)
        logger.debug("ActionExecutor stopped")

    # ------------------------------------------------------------------ #
    # Public                                                               #
    # ------------------------------------------------------------------ #

    def execute(self, action: dict[str, Any]) -> None:
        """Enqueue an action for asynchronous execution."""
        if self.enabled:
            self._queue.put(action)

    def clear_queue(self) -> None:
        """Drain all pending actions (emergency stop)."""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except Empty:
                break

    # ------------------------------------------------------------------ #
    # Worker                                                               #
    # ------------------------------------------------------------------ #

    def _worker(self) -> None:
        while not self._stop_event.is_set():
            try:
                action = self._queue.get(timeout=0.1)
            except Empty:
                continue

            try:
                self._dispatch(action)
            except Exception as exc:
                logger.error("Action execution error: %s", exc)
            finally:
                self._queue.task_done()

    def _dispatch(self, action: dict[str, Any]) -> None:
        action_type = action.get("type", "hotkey")

        if action_type == "hotkey":
            self._press_hotkey(action.get("keys", []))

        elif action_type == "sequence":
            steps = action.get("sequence", [])
            for step in steps:
                step_type = step.get("type")
                if step_type == "hotkey":
                    self._press_hotkey(step.get("keys", []))
                elif step_type == "delay":
                    ms = int(step.get("ms", 0))
                    time.sleep(ms / 1000.0)
                elif step_type == "key":
                    k = step.get("key", "")
                    if k:
                        keyboard.press_and_release(k)

    @staticmethod
    def _press_hotkey(keys: list[str]) -> None:
        """
        Press a combination of keys.

        keys = ["alt", "1"]  ->  Alt+1
        keys = ["ctrl", "shift", "f2"]  ->  Ctrl+Shift+F2
        """
        if not keys:
            return

        clean = [k.strip().lower() for k in keys if k.strip()]
        if not clean:
            return

        if len(clean) == 1:
            keyboard.press_and_release(clean[0])
        else:
            combo = "+".join(clean)
            keyboard.press_and_release(combo)

        logger.debug("Pressed: %s", "+".join(clean))

    # ------------------------------------------------------------------ #
    # Helpers: parse human-readable key strings                           #
    # ------------------------------------------------------------------ #

    @staticmethod
    def parse_hotkey_string(hotkey_str: str) -> list[str]:
        """
        Parse 'Alt+1', 'Ctrl+Shift+F2' etc. into a list of key names.
        Returns empty list on failure.
        """
        if not hotkey_str:
            return []
        return [part.strip().lower() for part in hotkey_str.split("+") if part.strip()]

    @staticmethod
    def keys_to_display_string(keys: list[str]) -> str:
        """Convert ['ctrl', 'shift', 'f2'] -> 'Ctrl+Shift+F2'"""
        return "+".join(k.capitalize() for k in keys)
