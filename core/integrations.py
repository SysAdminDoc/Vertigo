"""Optional-integration readiness and transient credential probes.

This module is intentionally side-effect light: readiness checks inspect the
current process and PATH, while credential validation sends one bounded HTTP
request only after the user asks for it. Secrets are never returned in a
result, written to settings, or included in diagnostics.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
from dataclasses import dataclass
from typing import Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class IntegrationDefinition:
    id: str
    label: str
    description: str
    packages: tuple[tuple[str, str], ...]
    credential_env: str | None
    license_note: str
    fallback: str
    executable: str | None = None


@dataclass(frozen=True)
class IntegrationStatus:
    definition: IntegrationDefinition
    installed: tuple[str, ...]
    missing: tuple[str, ...]
    credential_configured: bool
    credential_label: str

    @property
    def package_state(self) -> str:
        if not self.definition.packages and self.definition.executable:
            return "installed" if self.installed else "missing"
        if not self.missing:
            return "installed"
        if self.installed:
            return "partial"
        return "missing"

    @property
    def state(self) -> str:
        if self.package_state == "missing":
            return "missing"
        if self.definition.credential_env and not self.credential_configured:
            return "needs credential"
        return "ready" if self.package_state == "installed" else "partial"

    @property
    def package_summary(self) -> str:
        if self.definition.executable:
            return self.definition.executable
        if not self.missing:
            return "All optional packages installed"
        if not self.installed:
            return "Optional package not installed"
        return "Missing: " + ", ".join(self.missing)


@dataclass(frozen=True)
class CredentialCheckResult:
    service: str
    ok: bool
    message: str
    status_code: int | None = None


INTEGRATIONS: tuple[IntegrationDefinition, ...] = (
    IntegrationDefinition(
        id="captions",
        label="Local AI captions",
        description="faster-whisper transcription with local burn-in.",
        packages=(("faster_whisper", "faster-whisper"),),
        credential_env=None,
        license_note="MIT code; model files follow their own terms.",
        fallback="Manual subtitle sidecars and no-caption export.",
    ),
    IntegrationDefinition(
        id="vad",
        label="Speech-aware trim",
        description="Silero VAD tightens trims to the outer speech edges.",
        packages=(("silero_vad", "silero-vad"),),
        credential_env=None,
        license_note="MIT.",
        fallback="Manual trim handles and auto-editor when installed.",
    ),
    IntegrationDefinition(
        id="animated_captions",
        label="Animated captions",
        description="pycaps adds per-word animated caption templates.",
        packages=(("pycaps", "pycaps"),),
        credential_env=None,
        license_note="Apache-2.0.",
        fallback="Built-in libass caption presets.",
    ),
    IntegrationDefinition(
        id="object_tracking",
        label="Object/person tracking",
        description="An opt-in OpenCV person/motion fallback extends tracking beyond the default face path; BoxMOT can stabilize IDs when installed.",
        packages=(("boxmot", "boxmot"),),
        credential_env=None,
        license_note="AGPL-3.0; review network-copyleft obligations for hosted use.",
        fallback="Built-in lightweight face tracking plus the opt-in HOG/motion fallback; center crop remains available.",
    ),
    IntegrationDefinition(
        id="silence_editor",
        label="Auto-editor silence cuts",
        description="The optional auto-editor CLI proposes speech-contiguous sections.",
        packages=(),
        credential_env=None,
        license_note="Unlicense.",
        fallback="Manual trim and the local VAD helper.",
        executable="auto-editor",
    ),
    IntegrationDefinition(
        id="highlights",
        label="AI highlight ranking",
        description="Lighthouse ranks high-energy moments when its model is installed.",
        packages=(("lighthouse", "lighthouse-ml"),),
        credential_env=None,
        license_note="Apache-2.0 code; model weights may have separate terms.",
        fallback="Dependency-free audio-energy highlight sweep.",
    ),
    IntegrationDefinition(
        id="diarization",
        label="Speaker diarization",
        description="pyannote labels who spoke when for future speaker-aware framing.",
        packages=(("pyannote", "pyannote.audio"),),
        credential_env="HF_TOKEN",
        license_note="MIT code; the default gated model requires accepting its Hugging Face terms.",
        fallback="Face tracking, center crop, and local captions remain available.",
    ),
    IntegrationDefinition(
        id="broll",
        label="Transcript-driven b-roll",
        description="KeyBERT + Pexels search with optional CLIP re-ranking.",
        packages=(
            ("keybert", "keybert"),
            ("pypexels", "pypexels"),
            ("open_clip", "open_clip_torch"),
        ),
        credential_env="PEXELS_API_KEY",
        license_note="MIT/Apache-2.0 code; Pexels API terms and attribution apply.",
        fallback="Stdlib keyword extraction, native Pexels ranking, or no b-roll.",
    ),
    IntegrationDefinition(
        id="keyframes",
        label="Smart thumbnail picker",
        description="Katna adds optional semantic thumbnail selection.",
        packages=(("katna", "Katna"),),
        credential_env=None,
        license_note="Apache-2.0.",
        fallback="Built-in OpenCV representative-frame picker.",
    ),
)


def inspect_integrations(
    *,
    environ: Mapping[str, str] | None = None,
) -> tuple[IntegrationStatus, ...]:
    """Return current package, executable, and environment-key readiness."""
    env = environ if environ is not None else os.environ
    statuses: list[IntegrationStatus] = []
    for definition in INTEGRATIONS:
        installed: list[str] = []
        missing: list[str] = []
        if definition.executable:
            if shutil.which(definition.executable):
                installed.append(definition.executable)
            else:
                missing.append(definition.executable)
        for module_name, package_name in definition.packages:
            if _module_available(module_name):
                installed.append(package_name)
            else:
                missing.append(package_name)
        configured = bool(definition.credential_env and env.get(definition.credential_env, "").strip())
        credential_label = (
            "Configured in environment"
            if configured
            else (f"{definition.credential_env} not configured" if definition.credential_env else "Not required")
        )
        statuses.append(
            IntegrationStatus(
                definition=definition,
                installed=tuple(installed),
                missing=tuple(missing),
                credential_configured=configured,
                credential_label=credential_label,
            )
        )
    return tuple(statuses)


def validate_credential(
    service: str,
    secret: str,
    *,
    timeout: float = 5.0,
    opener: Callable | None = None,
) -> CredentialCheckResult:
    """Validate one transient credential with a bounded, redacted request."""
    value = (secret or "").strip()
    if not value:
        return CredentialCheckResult(service, False, "Enter a credential or configure its environment variable.")

    if service == "huggingface":
        url = "https://huggingface.co/api/whoami-v2"
        headers = {"Authorization": f"Bearer {value}"}
        label = "Hugging Face"
    elif service == "pexels":
        url = "https://api.pexels.com/v1/videos/search?query=vertigo&per_page=1"
        headers = {"Authorization": value}
        label = "Pexels"
    else:
        return CredentialCheckResult(service, False, "Unknown credential service.")

    request = Request(url, headers=headers, method="GET")
    open_request = opener or urlopen
    try:
        with open_request(request, timeout=timeout) as response:
            status = int(response.getcode() or 200)
        if 200 <= status < 300:
            return CredentialCheckResult(service, True, f"{label} credential accepted.", status)
        return CredentialCheckResult(service, False, f"{label} rejected the credential (HTTP {status}).", status)
    except HTTPError as exc:
        return CredentialCheckResult(service, False, f"{label} rejected the credential (HTTP {exc.code}).", exc.code)
    except (URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", None) or "network check failed"
        return CredentialCheckResult(service, False, f"Could not reach {label}: {reason}.")


def _module_available(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False
