"""
trigger_dialog.py
Modal dialog for creating and editing trigger rules.
Supports single hotkey and multi-step sequence actions.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ui.styles import (
    ACCENT_PRIMARY,
    ACCENT_SECONDARY,
    BG_ELEVATED,
    BG_PANEL,
    BORDER_DEFAULT,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

logger = logging.getLogger(__name__)

_SEQUENCE_PLACEHOLDER = """\
# One action per line. Examples:
# alt+1
# wait 500
# ctrl+shift+f2
# f1
# wait 200
# ctrl+3
"""

_SEQUENCE_HELP = (
    "Enter one action per line.\n"
    "Hotkeys: alt+1 | ctrl+shift+f2 | f1\n"
    "Delay:   wait 500  (milliseconds)"
)


def _parse_sequence_text(text: str) -> list[dict[str, Any]]:
    """Parse human-readable sequence text into internal step list."""
    steps: list[dict[str, Any]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        lower = line.lower()
        if lower.startswith("wait "):
            try:
                ms = int(lower.split()[1])
                steps.append({"type": "delay", "ms": ms})
            except (ValueError, IndexError):
                pass
        else:
            keys = [k.strip().lower() for k in line.split("+") if k.strip()]
            if keys:
                steps.append({"type": "hotkey", "keys": keys})
    return steps


def _sequence_to_text(steps: list[dict[str, Any]]) -> str:
    """Convert internal step list back to human-readable text."""
    lines: list[str] = []
    for step in steps:
        t = step.get("type")
        if t == "delay":
            lines.append(f"wait {step.get('ms', 0)}")
        elif t == "hotkey":
            lines.append("+".join(step.get("keys", [])))
    return "\n".join(lines)


class TriggerDialog(QDialog):
    """
    Add / Edit trigger dialog.

    Pass an existing trigger dict to edit it; pass None to create a new one.
    Call `.get_trigger()` after accept() to retrieve the result.
    """

    def __init__(self, parent: QWidget | None = None, trigger: dict[str, Any] | None = None) -> None:
        super().__init__(parent)
        self._trigger = trigger
        self._result: dict[str, Any] | None = None
        self._setup_ui()
        if trigger:
            self._populate(trigger)
        self.setMinimumWidth(540)

    # ------------------------------------------------------------------ #
    # UI setup                                                             #
    # ------------------------------------------------------------------ #

    def _setup_ui(self) -> None:
        is_edit = self._trigger is not None
        self.setWindowTitle("Edit Trigger" if is_edit else "New Trigger")
        self.setModal(True)
        self.setStyleSheet(f"QDialog {{ background: {BG_PANEL}; }}")

        root = QVBoxLayout(self)
        root.setSpacing(16)
        root.setContentsMargins(24, 24, 24, 24)

        # ── Header ──────────────────────────────────────────────────── #
        header_label = QLabel("Edit Trigger" if is_edit else "New Trigger")
        header_label.setStyleSheet(
            f"font-size: 18px; font-weight: 700; color: {TEXT_PRIMARY}; margin-bottom: 4px;"
        )
        root.addWidget(header_label)

        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {BORDER_DEFAULT};")
        root.addWidget(sep)

        # ── Form ────────────────────────────────────────────────────── #
        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        def lbl(text: str) -> QLabel:
            l = QLabel(text)
            l.setStyleSheet(f"color: {TEXT_SECONDARY}; font-weight: 500;")
            return l

        # Name
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Trigger name (optional)")
        form.addRow(lbl("Name"), self._name_edit)

        # Trigger text
        self._trigger_edit = QLineEdit()
        self._trigger_edit.setPlaceholderText("Text to detect on screen…")
        form.addRow(lbl("Trigger Text *"), self._trigger_edit)

        # Match type
        self._match_combo = QComboBox()
        self._match_combo.addItems(["contains", "exact", "regex"])
        form.addRow(lbl("Match Type"), self._match_combo)

        # Case sensitive
        self._case_check = QCheckBox("Case sensitive")
        form.addRow(lbl(""), self._case_check)

        # Cooldown
        self._cooldown_spin = QSpinBox()
        self._cooldown_spin.setRange(0, 3600)
        self._cooldown_spin.setValue(3)
        self._cooldown_spin.setSuffix(" s")
        self._cooldown_spin.setToolTip("Minimum seconds between repeated triggers")
        form.addRow(lbl("Cooldown"), self._cooldown_spin)

        # Enabled
        self._enabled_check = QCheckBox("Enabled")
        self._enabled_check.setChecked(True)
        form.addRow(lbl(""), self._enabled_check)

        root.addLayout(form)

        # ── Action type ─────────────────────────────────────────────── #
        action_header = QLabel("ACTION")
        action_header.setStyleSheet(
            f"font-size: 11px; font-weight: 600; color: {TEXT_MUTED}; letter-spacing: 1.5px;"
        )
        root.addWidget(action_header)

        action_type_row = QHBoxLayout()
        action_type_label = QLabel("Type:")
        action_type_label.setStyleSheet(f"color: {TEXT_SECONDARY};")
        self._action_type_combo = QComboBox()
        self._action_type_combo.addItems(["hotkey", "sequence"])
        self._action_type_combo.currentTextChanged.connect(self._on_action_type_changed)
        action_type_row.addWidget(action_type_label)
        action_type_row.addWidget(self._action_type_combo)
        action_type_row.addStretch()
        root.addLayout(action_type_row)

        # Hotkey row
        self._hotkey_widget = QWidget()
        hotkey_layout = QHBoxLayout(self._hotkey_widget)
        hotkey_layout.setContentsMargins(0, 0, 0, 0)
        hotkey_label = QLabel("Keys:")
        hotkey_label.setStyleSheet(f"color: {TEXT_SECONDARY};")
        self._hotkey_edit = QLineEdit()
        self._hotkey_edit.setPlaceholderText("e.g. alt+1  or  ctrl+shift+f2")
        hotkey_hint = QLabel("Use + to separate keys")
        hotkey_hint.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        hotkey_layout.addWidget(hotkey_label)
        hotkey_layout.addWidget(self._hotkey_edit, 1)
        hotkey_layout.addWidget(hotkey_hint)
        root.addWidget(self._hotkey_widget)

        # Sequence editor
        self._sequence_widget = QWidget()
        seq_layout = QVBoxLayout(self._sequence_widget)
        seq_layout.setContentsMargins(0, 0, 0, 0)
        seq_hint = QLabel(_SEQUENCE_HELP)
        seq_hint.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        self._sequence_edit = QTextEdit()
        self._sequence_edit.setPlaceholderText(_SEQUENCE_PLACEHOLDER)
        self._sequence_edit.setMinimumHeight(130)
        self._sequence_edit.setMaximumHeight(200)
        seq_layout.addWidget(seq_hint)
        seq_layout.addWidget(self._sequence_edit)
        root.addWidget(self._sequence_widget)
        self._sequence_widget.hide()

        # ── Button box ──────────────────────────────────────────────── #
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        save_btn = buttons.button(QDialogButtonBox.StandardButton.Save)
        cancel_btn = buttons.button(QDialogButtonBox.StandardButton.Cancel)

        save_btn.setObjectName("PrimaryButton")
        save_btn.setMinimumWidth(100)
        cancel_btn.setObjectName("SecondaryButton")
        cancel_btn.setMinimumWidth(80)

        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    # ------------------------------------------------------------------ #
    # Slots                                                                #
    # ------------------------------------------------------------------ #

    def _on_action_type_changed(self, action_type: str) -> None:
        is_hotkey = action_type == "hotkey"
        self._hotkey_widget.setVisible(is_hotkey)
        self._sequence_widget.setVisible(not is_hotkey)

    def _on_save(self) -> None:
        trigger_text = self._trigger_edit.text().strip()
        if not trigger_text:
            QMessageBox.warning(self, "Validation Error", "Trigger text cannot be empty.")
            return

        action_type = self._action_type_combo.currentText()
        action: dict[str, Any] = {"type": action_type}

        if action_type == "hotkey":
            raw_keys = self._hotkey_edit.text().strip()
            if not raw_keys:
                QMessageBox.warning(self, "Validation Error", "Please enter at least one key.")
                return
            keys = [k.strip().lower() for k in raw_keys.split("+") if k.strip()]
            action["keys"] = keys
        else:
            seq_text = self._sequence_edit.toPlainText()
            steps = _parse_sequence_text(seq_text)
            if not steps:
                QMessageBox.warning(
                    self, "Validation Error",
                    "Sequence is empty or invalid.\nAdd at least one hotkey or delay step."
                )
                return
            action["sequence"] = steps

        existing_id = self._trigger.get("id") if self._trigger else None

        self._result = {
            "id": existing_id or str(uuid.uuid4()),
            "name": self._name_edit.text().strip() or trigger_text,
            "enabled": self._enabled_check.isChecked(),
            "trigger": trigger_text,
            "match_type": self._match_combo.currentText(),
            "case_sensitive": self._case_check.isChecked(),
            "cooldown": self._cooldown_spin.value(),
            "action": action,
        }
        self.accept()

    # ------------------------------------------------------------------ #
    # Populate from existing trigger                                       #
    # ------------------------------------------------------------------ #

    def _populate(self, t: dict[str, Any]) -> None:
        self._name_edit.setText(t.get("name", ""))
        self._trigger_edit.setText(t.get("trigger", ""))

        match_type = t.get("match_type", "contains")
        idx = self._match_combo.findText(match_type)
        if idx >= 0:
            self._match_combo.setCurrentIndex(idx)

        self._case_check.setChecked(bool(t.get("case_sensitive", False)))
        self._cooldown_spin.setValue(int(t.get("cooldown", 3)))
        self._enabled_check.setChecked(bool(t.get("enabled", True)))

        action = t.get("action", {})
        action_type = action.get("type", "hotkey")
        idx2 = self._action_type_combo.findText(action_type)
        if idx2 >= 0:
            self._action_type_combo.setCurrentIndex(idx2)

        if action_type == "hotkey":
            keys = action.get("keys", [])
            self._hotkey_edit.setText("+".join(keys))
        else:
            steps = action.get("sequence", [])
            self._sequence_edit.setPlainText(_sequence_to_text(steps))

    # ------------------------------------------------------------------ #
    # Result                                                               #
    # ------------------------------------------------------------------ #

    def get_trigger(self) -> dict[str, Any] | None:
        """Call after exec() == QDialog.Accepted to get the trigger dict."""
        return self._result
