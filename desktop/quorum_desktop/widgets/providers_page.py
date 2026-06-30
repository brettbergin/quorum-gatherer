"""Providers settings page — progressive staged flow with per-role model selection.

Select a provider, paste its key, then **Test key & load models**: that one call authenticates the
key *and* fetches the live model catalog the account actually has access to. Models are then chosen
*per council role* — the deliberating council members and the synthesizing Chairman get their own
model (and, where the model supports it, a provider-specific reasoning knob). This keeps the
Chairman on a capable synthesis model instead of being downgraded with the members. **Save**
persists.
"""

from __future__ import annotations

import asyncio
import re

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from quorum_desktop import engine


def _wide_combo() -> QComboBox:
    c = QComboBox()
    c.setMinimumWidth(360)
    c.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    c.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
    c.view().setMinimumWidth(360)
    return c


class _ModelReasoningField(QWidget):
    """A model dropdown plus its provider-specific reasoning control, for one council role.

    The reasoning control mirrors the provider's *raw* knob: an effort dropdown, a thinking-budget
    spinner, or nothing. It enables only when the selected model supports reasoning.
    """

    def __init__(self, role_label: str) -> None:
        super().__init__()
        self._spec: dict | None = None
        self._models: list[dict] = []
        self._locked = True

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        heading = QLabel(role_label)
        heading.setObjectName("agentName")
        layout.addWidget(heading)

        self.model = _wide_combo()
        self.model.currentIndexChanged.connect(lambda _i: self._refresh_reasoning())
        layout.addWidget(self.model)

        self._reasoning_row = QWidget()
        rl = QHBoxLayout(self._reasoning_row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(QLabel("Reasoning"))
        self._effort = QComboBox()  # kind="effort"
        self._budget_enable = QCheckBox("Enable")  # kind="thinking_budget"
        self._budget = QSpinBox()
        self._budget.setSuffix(" tokens")
        self._budget_enable.toggled.connect(self._budget.setEnabled)
        self._hint = QLabel("")
        self._hint.setObjectName("muted")
        rl.addWidget(self._effort)
        rl.addWidget(self._budget_enable)
        rl.addWidget(self._budget, 1)
        rl.addWidget(self._hint, 1)
        layout.addWidget(self._reasoning_row)

    # --- configuration -----------------------------------------------------
    def configure(self, spec: dict | None) -> None:
        """Set the provider spec and lay out the matching reasoning variant."""
        self._spec = spec
        kind = self._kind()
        has_reasoning = kind != "none"
        self._reasoning_row.setVisible(has_reasoning)
        is_effort = kind == "effort"
        is_budget = kind == "thinking_budget"
        self._effort.setVisible(is_effort)
        self._budget_enable.setVisible(is_budget)
        self._budget.setVisible(is_budget)

        if is_effort and spec is not None:
            self._effort.blockSignals(True)
            self._effort.clear()
            self._effort.addItem("Off", "")
            for e in spec["reasoning"]["efforts"]:
                self._effort.addItem(e, e)
            self._effort.blockSignals(False)
        elif is_budget and spec is not None:
            r = spec["reasoning"]
            self._budget.setRange(max(1, r["budget_min"]), r["budget_max"])
            self._budget.setValue(r["budget_default"] or max(1, r["budget_min"]))

    def preview_stored(self, stored_model: str | None, stored_reasoning: str | None) -> None:
        """Before a catalog is loaded, show the currently-configured model (locked)."""
        self._models = []
        self._locked = True
        self.model.blockSignals(True)
        self.model.clear()
        if stored_model:
            self.model.addItem(stored_model, stored_model)
            self.model.setCurrentIndex(0)
        self.model.setEnabled(False)
        self.model.blockSignals(False)
        self._apply_stored_reasoning(stored_reasoning)
        self._refresh_reasoning()

    def load_catalog(
        self, models: list[dict], stored_model: str | None, stored_reasoning: str | None
    ) -> None:
        """After Test, populate from the live catalog and pre-select the stored model."""
        self._models = models
        self._locked = False
        self.model.blockSignals(True)
        self.model.clear()
        for m in models:
            label = m["label"] if m["label"] == m["id"] else f"{m['label']} ({m['id']})"
            self.model.addItem(label, m["id"])
        self.model.setEnabled(bool(models))
        if stored_model:
            idx = self.model.findData(stored_model)
            if idx >= 0:
                self.model.setCurrentIndex(idx)
        self.model.blockSignals(False)
        self._apply_stored_reasoning(stored_reasoning)
        self._refresh_reasoning()

    # --- readers -----------------------------------------------------------
    def model_id(self) -> str | None:
        return self.model.currentData() or None

    def reasoning_raw(self) -> str:
        """Raw reasoning value to persist — "" clears it."""
        kind = self._kind()
        model = self._selected_model()
        if kind == "none" or not (model and model.get("supports_reasoning")):
            return ""
        if kind == "effort":
            return self._effort.currentData() or ""
        if kind == "thinking_budget":
            return str(self._budget.value()) if self._budget_enable.isChecked() else ""
        return ""

    # --- internals ---------------------------------------------------------
    def _kind(self) -> str:
        return (self._spec or {}).get("reasoning", {}).get("kind", "none")

    def _selected_model(self) -> dict | None:
        mid = self.model.currentData()
        if not mid:
            return None
        found = next((m for m in self._models if m["id"] == mid), None)
        if found is not None:
            return found
        # Catalog not loaded yet: synthesize so reasoning reflects the stored model's capability.
        pattern = (self._spec or {}).get("reasoning", {}).get("model_pattern", "")
        supports = bool(pattern) and re.search(pattern, mid, re.IGNORECASE) is not None
        return {"id": mid, "label": mid, "supports_reasoning": supports}

    def _apply_stored_reasoning(self, stored: str | None) -> None:
        kind = self._kind()
        if kind == "effort":
            idx = self._effort.findData(stored) if stored else 0
            self._effort.setCurrentIndex(idx if idx >= 0 else 0)
        elif kind == "thinking_budget":
            if stored and stored.isdigit():
                self._budget_enable.setChecked(True)
                self._budget.setValue(int(stored))
            else:
                self._budget_enable.setChecked(False)

    def _refresh_reasoning(self) -> None:
        """Enable the reasoning control only when the model supports it and we're unlocked."""
        kind = self._kind()
        if kind == "none":
            return
        model = self._selected_model()
        supported = bool(model and model.get("supports_reasoning"))
        active = supported and not self._locked
        if kind == "effort":
            self._effort.setEnabled(active)
            if not supported:
                self._effort.setCurrentIndex(0)
        elif kind == "thinking_budget":
            self._budget_enable.setEnabled(active)
            self._budget.setEnabled(active and self._budget_enable.isChecked())
            if not supported:
                self._budget_enable.setChecked(False)
        self._hint.setText("" if supported else "No reasoning for this model.")


class ProvidersPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._state: dict = {"specs": [], "settings": {}}
        self._models: list[dict] = []  # live catalog for the current provider

        outer = QVBoxLayout(self)
        title = QLabel("AI provider")
        title.setStyleSheet("font-size:16px; font-weight:700;")
        outer.addWidget(title)
        blurb = QLabel(
            "Choose a provider and paste its API key, then Test it. The key is validated and the "
            "models you have access to are loaded. Pick a model for the council members and for "
            "the Chairman, set reasoning where available, then Save."
        )
        blurb.setObjectName("muted")
        blurb.setWordWrap(True)
        outer.addWidget(blurb)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self._provider = _wide_combo()
        self._provider.currentIndexChanged.connect(self._on_provider_changed)

        # API key + Test button on one row.
        self._key = QLineEdit()
        self._key.setEchoMode(QLineEdit.EchoMode.Password)
        self._key.textEdited.connect(self._on_key_edited)
        self._test = QPushButton("Test key && load models")
        self._test.clicked.connect(lambda: self._spawn(self._do_test()))
        key_row = QHBoxLayout()
        key_row.addWidget(self._key, 1)
        key_row.addWidget(self._test)

        form.addRow("Provider", self._provider)
        form.addRow("API key", key_row)
        outer.addLayout(form)

        # Per-role model + reasoning sections.
        self._members = _ModelReasoningField("Council members")
        self._chairman = _ModelReasoningField("Chairman (synthesis)")
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setObjectName("muted")
        outer.addWidget(self._members)
        outer.addWidget(divider)
        outer.addWidget(self._chairman)

        actions = QHBoxLayout()
        self._badge = QLabel("not configured")
        self._badge.setObjectName("badge")
        self._disable = QPushButton("Disable")
        self._disable.clicked.connect(lambda: self._spawn(self._do_disable()))
        self._save = QPushButton("Save")
        self._save.setObjectName("primary")
        self._save.setEnabled(False)
        self._save.clicked.connect(lambda: self._spawn(self._do_save()))
        actions.addWidget(self._badge)
        actions.addStretch(1)
        actions.addWidget(self._disable)
        actions.addWidget(self._save)
        outer.addLayout(actions)

        self._status = QLabel("")
        self._status.setObjectName("statusLine")
        self._status.setWordWrap(True)
        outer.addWidget(self._status)
        outer.addStretch(1)

        self._spawn(self._load())

    # ----------------------------------------------------------------- helpers
    @staticmethod
    def _spawn(coro) -> None:
        asyncio.ensure_future(coro)

    def _set_status(self, text: str, state: str) -> None:
        self._status.setText(text)
        self._status.setProperty("state", state)
        self._status.style().unpolish(self._status)
        self._status.style().polish(self._status)

    def _set_badge(self, text: str, state: str = "") -> None:
        self._badge.setText(text)
        self._badge.setProperty("state", state)
        self._badge.style().unpolish(self._badge)
        self._badge.style().polish(self._badge)

    def _current_spec(self) -> dict | None:
        key = self._provider.currentData()
        return next((s for s in self._state["specs"] if s["key"] == key), None)

    def _current_setting(self) -> dict | None:
        return self._state["settings"].get(self._provider.currentData())

    # ----------------------------------------------------------------- load / provider change
    async def _load(self) -> None:
        self._state = await engine.provider_state()
        self._provider.blockSignals(True)
        self._provider.clear()
        for spec in self._state["specs"]:
            s = self._state["settings"].get(spec["key"])
            tag = (
                " ✓ enabled"
                if s and s["is_enabled"]
                else " (disabled)"
                if s and s["has_key"]
                else ""
            )
            self._provider.addItem(spec["label"] + tag, spec["key"])
        self._provider.blockSignals(False)
        self._on_provider_changed()

    def _on_provider_changed(self) -> None:
        spec = self._current_spec()
        setting = self._current_setting() or {}
        self._models = []
        self._key.clear()
        self._key.setPlaceholderText(
            "•••••••• stored — leave blank to reuse" if setting.get("has_key") else "Paste API key"
        )
        # Models + reasoning stay locked until the key is tested; show the configured models.
        self._members.configure(spec)
        self._members.preview_stored(setting.get("default_model"), setting.get("reasoning"))
        self._chairman.configure(spec)
        self._chairman.preview_stored(
            setting.get("chairman_model"), setting.get("chairman_reasoning")
        )
        self._save.setEnabled(False)

        if setting.get("is_enabled"):
            self._set_badge("enabled", "enabled")
        elif setting.get("has_key"):
            self._set_badge("disabled", "disabled")
        else:
            self._set_badge("not configured", "")
        self._disable.setEnabled(bool(setting.get("has_key")))
        self._set_status("Test the key to load this provider's models." if spec else "", "")

    def _on_key_edited(self, _text: str) -> None:
        # A changed key invalidates the loaded catalog — require a re-test before saving.
        self._models = []
        self._save.setEnabled(False)
        setting = self._current_setting() or {}
        self._members.preview_stored(setting.get("default_model"), setting.get("reasoning"))
        self._chairman.preview_stored(
            setting.get("chairman_model"), setting.get("chairman_reasoning")
        )

    # ----------------------------------------------------------------- actions
    async def _do_test(self) -> None:
        self._test.setEnabled(False)
        self._set_status("Validating key and loading models…", "applying")
        provider = self._provider.currentData()
        try:
            self._models = await engine.fetch_models(provider, self._key.text() or None)
        except Exception as exc:  # noqa: BLE001 - surface provider/auth errors to the user
            self._test.setEnabled(True)
            self._models = []
            self._save.setEnabled(False)
            self._set_status(f"⚠ {self._short(exc)}", "error")
            return
        self._test.setEnabled(True)

        setting = self._current_setting() or {}
        self._members.load_catalog(
            self._models, setting.get("default_model"), setting.get("reasoning")
        )
        self._chairman.load_catalog(
            self._models, setting.get("chairman_model"), setting.get("chairman_reasoning")
        )
        self._save.setEnabled(bool(self._models))

        if self._models:
            self._set_badge("key valid", "valid")
            self._set_status(f"✓ Key valid — {len(self._models)} models loaded.", "ok")
        else:
            self._set_status("Key valid, but no models were returned.", "error")

    async def _do_save(self) -> None:
        self._save.setEnabled(False)
        self._set_status("Validating and saving…", "applying")
        provider = self._provider.currentData()
        ok, error = await engine.apply_provider(
            provider,
            self._key.text() or None,
            self._members.model_id(),
            self._members.reasoning_raw(),
            self._chairman.model_id(),
            self._chairman.reasoning_raw(),
        )
        self._save.setEnabled(True)
        if ok:
            await self._load()
            self._set_status("✓ Saved — provider enabled.", "ok")
        else:
            self._set_status(f"⚠ {error}", "error")

    async def _do_disable(self) -> None:
        provider = self._provider.currentData()
        await engine.disable_provider(provider)
        await self._load()
        self._set_status("Provider disabled.", "")

    @staticmethod
    def _short(exc: Exception) -> str:
        msg = str(exc).strip() or exc.__class__.__name__
        return msg.splitlines()[0][:300] if msg else exc.__class__.__name__
