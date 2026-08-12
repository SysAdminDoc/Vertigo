"""Optional-integration readiness and redacted credential-check coverage."""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch


class _FakeResponse:
    def __init__(self, status: int = 200) -> None:
        self.status = status

    def getcode(self) -> int:
        return self.status

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None


class OptionalReadinessTests(unittest.TestCase):
    def test_empty_environment_reports_fallbacks_and_missing_credentials(self) -> None:
        from core.integrations import inspect_integrations

        statuses = inspect_integrations(environ={})
        by_id = {status.definition.id: status for status in statuses}

        self.assertIn("diarization", by_id)
        self.assertEqual(by_id["diarization"].state, "missing")
        self.assertIn("HF_TOKEN not configured", by_id["diarization"].credential_label)
        self.assertIn("available", by_id["diarization"].definition.fallback.lower())
        self.assertIn("broll", by_id)
        self.assertTrue(by_id["broll"].definition.license_note)

    def test_environment_presence_is_reported_without_exposing_secret(self) -> None:
        from core.integrations import inspect_integrations

        statuses = inspect_integrations(environ={"HF_TOKEN": "hf_private_value"})
        diarization = next(status for status in statuses if status.definition.id == "diarization")

        self.assertTrue(diarization.credential_configured)
        self.assertEqual(diarization.credential_label, "Configured in environment")
        self.assertNotIn("private_value", diarization.credential_label)

    def test_huggingface_probe_sends_bearer_header_without_echoing_secret(self) -> None:
        from core.integrations import validate_credential

        captured: dict = {}

        def opener(request, *, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return _FakeResponse()

        result = validate_credential(
            "huggingface",
            "hf_test_secret",
            timeout=3.0,
            opener=opener,
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(captured["request"].get_header("Authorization"), "Bearer hf_test_secret")
        self.assertEqual(captured["timeout"], 3.0)
        self.assertNotIn("hf_test_secret", result.message)

    def test_pexels_probe_rejects_http_failure_without_echoing_secret(self) -> None:
        from urllib.error import HTTPError

        from core.integrations import validate_credential

        def opener(_request, *, timeout):
            raise HTTPError("https://api.pexels.com", 401, "unauthorized", {}, None)

        result = validate_credential("pexels", "pexels_secret", opener=opener)

        self.assertFalse(result.ok)
        self.assertEqual(result.status_code, 401)
        self.assertIn("HTTP 401", result.message)
        self.assertNotIn("pexels_secret", result.message)

    @classmethod
    def setUpClass(cls) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        os.environ.setdefault("QT_ANIMATION_DURATION_FACTOR", "0")
        from PyQt6.QtWidgets import QApplication

        cls._app = QApplication.instance() or QApplication(sys.argv)
        from ui.theme import apply_app_theme

        apply_app_theme(cls._app, "mocha")

    def test_main_window_opens_readiness_panel_with_all_rows(self) -> None:
        from core.integrations import INTEGRATIONS
        from ui.integrations_panel import IntegrationReadinessPanel
        from ui.main_window import MainWindow

        with patch.dict(os.environ, {}, clear=False):
            win = MainWindow()
            try:
                win._show_integrations()
                panel = win._integration_dialog.findChild(IntegrationReadinessPanel)
                self.assertIsNotNone(panel)
                assert panel is not None
                self.assertEqual(len(panel._rows), len(INTEGRATIONS))
                self.assertTrue(win._integrations_btn.accessibleName())
            finally:
                if win._integration_dialog is not None:
                    win._integration_dialog.close()
                win.close()
                win.deleteLater()


if __name__ == "__main__":
    unittest.main()
