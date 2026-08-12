"""Optional-integration readiness panel with transient credential checks."""

from __future__ import annotations

import os

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.integrations import (
    CredentialCheckResult,
    IntegrationStatus,
    inspect_integrations,
    validate_credential,
)


class _CredentialWorker(QThread):
    checked = pyqtSignal(object)

    def __init__(self, service: str, secret: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self._secret = secret

    def run(self) -> None:
        try:
            result = validate_credential(self._service, self._secret)
        except Exception as exc:
            result = CredentialCheckResult(
                self._service,
                False,
                f"Credential check failed: {type(exc).__name__}.",
            )
        finally:
            # Do not retain the user's secret on the worker after the request.
            self._secret = ""
        self.checked.emit(result)


class IntegrationReadinessPanel(QWidget):
    """List optional tools, prerequisites, fallbacks, and license notes."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: dict[str, dict] = {}
        self._workers: dict[str, _CredentialWorker] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("Optional tools stay local and opt-in")
        title.setObjectName("valueBright")
        header.addWidget(title)
        header.addStretch(1)
        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setObjectName("ghostBtn")
        self._refresh_btn.setAccessibleName("Refresh optional integration readiness")
        self._refresh_btn.clicked.connect(self.refresh)
        header.addWidget(self._refresh_btn)
        root.addLayout(header)

        intro = QLabel(
            "Install only the capabilities you need. Missing tools keep their existing local fallback. "
            "Credential checks make one request only; typed secrets are cleared after the response and are "
            "never written to settings, manifests, or logs."
        )
        intro.setObjectName("subtitle")
        intro.setWordWrap(True)
        root.addWidget(intro)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("background: transparent;")
        self._host = QWidget()
        self._list = QVBoxLayout(self._host)
        self._list.setContentsMargins(0, 0, 8, 0)
        self._list.setSpacing(8)
        self._scroll.setWidget(self._host)
        root.addWidget(self._scroll, 1)

        self.refresh()

    def refresh(self) -> None:
        statuses = inspect_integrations()
        if not self._rows:
            for status in statuses:
                self._add_row(status)
        else:
            for status in statuses:
                self._update_row(status)

    def shutdown(self, timeout_ms: int = 1500) -> None:
        """Join any in-flight credential probe before the window exits."""
        for worker in list(self._workers.values()):
            if worker.isRunning() and not worker.wait(timeout_ms):
                worker.terminate()
                worker.wait(250)
        self._workers.clear()

    def closeEvent(self, event) -> None:
        self.shutdown()
        super().closeEvent(event)

    def _add_row(self, status: IntegrationStatus) -> None:
        definition = status.definition
        card = QFrame()
        card.setObjectName("queueItem")
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(4)

        top = QHBoxLayout()
        name = QLabel(definition.label)
        name.setObjectName("valueBright")
        top.addWidget(name)
        top.addStretch(1)
        badge = QLabel("")
        badge.setObjectName("statusPill")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setMinimumWidth(112)
        top.addWidget(badge)
        lay.addLayout(top)

        desc = QLabel(definition.description)
        desc.setObjectName("subtitle")
        desc.setWordWrap(True)
        lay.addWidget(desc)

        package = QLabel("")
        package.setObjectName("valueMuted")
        package.setWordWrap(True)
        lay.addWidget(package)

        credential = QLabel("")
        credential.setObjectName("valueMuted")
        credential.setWordWrap(True)
        lay.addWidget(credential)

        license_label = QLabel(f"License / terms: {definition.license_note}")
        license_label.setObjectName("valueMuted")
        license_label.setWordWrap(True)
        lay.addWidget(license_label)

        fallback = QLabel(f"Fallback: {definition.fallback}")
        fallback.setObjectName("valueMuted")
        fallback.setWordWrap(True)
        lay.addWidget(fallback)

        secret_edit = None
        validate_btn = None
        validation = None
        if definition.credential_env:
            credential_row = QHBoxLayout()
            secret_edit = QLineEdit()
            secret_edit.setEchoMode(QLineEdit.EchoMode.Password)
            secret_edit.setPlaceholderText(
                f"Paste {definition.credential_env} for a one-request check (not saved)"
            )
            secret_edit.setAccessibleName(f"{definition.credential_env} credential")
            credential_row.addWidget(secret_edit, 1)
            validate_btn = QPushButton("Validate")
            validate_btn.setObjectName("ghostBtn")
            validate_btn.setAccessibleName(f"Validate {definition.label} credential")
            service = "huggingface" if definition.credential_env == "HF_TOKEN" else "pexels"
            validate_btn.clicked.connect(
                lambda _=False, key=definition.id, service_name=service: self._validate(
                    key, service_name
                )
            )
            credential_row.addWidget(validate_btn)
            lay.addLayout(credential_row)
            validation = QLabel("")
            validation.setObjectName("valueMuted")
            validation.setWordWrap(True)
            lay.addWidget(validation)

        self._rows[definition.id] = {
            "card": card,
            "badge": badge,
            "package": package,
            "credential": credential,
            "edit": secret_edit,
            "validate": validate_btn,
            "validation": validation,
        }
        self._list.addWidget(card)
        self._update_row(status)
        self._list.addStretch(1)

    def _update_row(self, status: IntegrationStatus) -> None:
        row = self._rows[status.definition.id]
        row["badge"].setText(status.state.title())
        tone = {
            "ready": "success",
            "partial": "accent",
            "needs credential": "warning",
            "missing": "warning",
        }.get(status.state, "warning")
        row["badge"].setProperty("tone", tone)
        row["badge"].style().unpolish(row["badge"])
        row["badge"].style().polish(row["badge"])
        row["package"].setText(f"Packages: {status.package_summary}")
        row["credential"].setText(f"Credential: {status.credential_label}")
        if row["validate"] is not None:
            row["validate"].setEnabled(status.definition.credential_env is not None)

    def _validate(self, integration_id: str, service: str) -> None:
        row = self._rows[integration_id]
        if service in self._workers and self._workers[service].isRunning():
            return
        edit: QLineEdit = row["edit"]
        definition_env = "HF_TOKEN" if service == "huggingface" else "PEXELS_API_KEY"
        secret = edit.text().strip() or os.environ.get(definition_env, "").strip()
        if not secret:
            row["validation"].setText(f"Enter a value or configure {definition_env} in the environment.")
            row["validation"].setProperty("tone", "warning")
            return
        row["validation"].setText("Checking credential…")
        row["validate"].setEnabled(False)
        worker = _CredentialWorker(service, secret, self)
        worker.checked.connect(
            lambda result, key=integration_id, service_name=service: self._on_checked(
                key, service_name, result
            )
        )
        worker.finished.connect(worker.deleteLater)
        self._workers[service] = worker
        worker.start()

    def _on_checked(self, integration_id: str, service: str, result: CredentialCheckResult) -> None:
        row = self._rows[integration_id]
        row["edit"].clear()
        row["validation"].setText(result.message)
        row["validation"].setProperty("tone", "success" if result.ok else "warning")
        row["validation"].style().unpolish(row["validation"])
        row["validation"].style().polish(row["validation"])
        row["validate"].setEnabled(True)
        self._workers.pop(service, None)
