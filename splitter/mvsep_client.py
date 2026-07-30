"""Small, opt-in client for the hosted MVSep separation API.

This adapter is intentionally separate from the local and Modal runners.  It
uses the documented MVSep API contract and never runs unless the caller has
explicitly selected the experimental profile and configured an API token.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urljoin

import requests

from .util import ensure_dir


class MVSEPError(RuntimeError):
    """A structured MVSep adapter failure."""


class MVSEPClient:
    """Client for MVSep's documented separation API."""

    # Use one explicit regional host so create, polling, and downloads stay
    # on the same region. MVSep recommends de2 for callers outside Europe and
    # North Asia; deployments can override this with MVSEP_API_BASE_URL.
    DEFAULT_BASE_URL = "https://de2.mvsep.com/api"

    # These are the documented separation type IDs and option defaults for
    # the specialist families currently being evaluated.
    MODELS: dict[str, dict[str, object]] = {
        "MVSep-Piano": {"sep_type": 29, "add_opt1": "5"},
        "MVSep-Guitar": {"sep_type": 31, "add_opt1": "7"},
        "MVSep-Acoustic-Guitar": {"sep_type": 66, "add_opt2": "0"},
        "MVSep-Electric-Guitar": {"sep_type": 81, "add_opt2": "0"},
        "MVSep-Bowed-Strings": {"sep_type": 52, "add_opt1": "1", "add_opt2": "0"},
        "MVSep-Wind": {"sep_type": 54, "add_opt1": "3", "add_opt2": "0", "add_opt3": "0"},
        "MVSep-Synth": {"sep_type": 88, "add_opt1": "0"},
        "DrumSep": {"sep_type": 37, "add_opt1": "7", "add_opt2": "0"},
    }

    # Backward-compatible names are retained only as aliases for callers that
    # used the old experimental module; the job pipeline uses the names above.
    MODEL_ALIASES = {
        "MVSep-Lead-Guitar": "MVSep-Guitar",
        "MVSep-Plucked-Strings": "MVSep-Bowed-Strings",
        "MVSep-Keys": "MVSep-Synth",
    }

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        base_url: str | None = None,
        timeout: int = 300,
        max_retries: int = 3,
        retry_delay: int = 5,
        poll_interval: int = 5,
        max_polls: int = 720,
    ) -> None:
        self.api_key = api_key
        self.base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.poll_interval = poll_interval
        self.max_polls = max_polls
        self.session = requests.Session()

    def separate(
        self,
        input_path: Path,
        model: str,
        output_dir: Path,
        output_format: str = "wav",
    ) -> Dict[str, Path]:
        """Run one MVSep model and download its output files."""
        model_name = self.MODEL_ALIASES.get(model, model)
        model_config = self.MODELS.get(model_name)
        if model_config is None:
            raise MVSEPError(f"mvsep_unknown_model:{model}")
        if not self.api_key:
            raise MVSEPError("mvsep_api_key_missing")
        if not input_path.exists():
            raise MVSEPError("mvsep_input_missing")

        ensure_dir(output_dir)
        for attempt in range(self.max_retries):
            try:
                return self._separate_once(
                    input_path=input_path,
                    output_dir=output_dir,
                    model_name=model_name,
                    model_config=model_config,
                    output_format=output_format,
                )
            except (MVSEPError, requests.RequestException):
                if attempt >= self.max_retries - 1:
                    raise
                time.sleep(self.retry_delay * (attempt + 1))
        raise MVSEPError("mvsep_retry_exhausted")

    def _separate_once(
        self,
        *,
        input_path: Path,
        output_dir: Path,
        model_name: str,
        model_config: dict[str, object],
        output_format: str,
    ) -> Dict[str, Path]:
        response_format = {"wav": 1, "flac": 2, "mp3": 0}.get(output_format.lower())
        if response_format is None:
            raise MVSEPError(f"mvsep_output_format_unsupported:{output_format}")

        fields = {
            "api_token": self.api_key,
            "sep_type": str(model_config["sep_type"]),
            "output_format": str(response_format),
            "is_demo": "0",
        }
        for option_name in ("add_opt1", "add_opt2", "add_opt3"):
            if option_name in model_config:
                fields[option_name] = str(model_config[option_name])

        with input_path.open("rb") as audio_file:
            response = self.session.post(
                f"{self.base_url}/separation/create",
                files={"audiofile": (input_path.name, audio_file)},
                data=fields,
                timeout=self.timeout,
            )
        response.raise_for_status()
        created = self._json(response)
        if not created.get("success"):
            raise MVSEPError(f"mvsep_create_failed:{self._message(created)}")

        data = created.get("data")
        if not isinstance(data, dict) or not data.get("hash"):
            raise MVSEPError("mvsep_create_missing_hash")

        result = self._poll_result(str(data["hash"]))
        files = self._extract_files(result)
        if not files:
            raise MVSEPError(f"mvsep_result_missing_files:{model_name}")

        downloaded: Dict[str, Path] = {}
        for stem_name, stem_url in files.items():
            downloaded[stem_name] = self._download_stem(stem_url, output_dir, stem_name)
        return downloaded

    def _poll_result(self, job_hash: str) -> dict[str, Any]:
        for _ in range(self.max_polls):
            response = self.session.get(
                f"{self.base_url}/separation/get",
                params={"hash": job_hash},
                timeout=min(self.timeout, 60),
            )
            response.raise_for_status()
            payload = self._json(response)
            status = self._status(payload)
            if status in {"done", "completed", "complete"}:
                return payload
            if status in {"failed", "error", "not_found", "cancelled"}:
                raise MVSEPError(f"mvsep_job_{status}:{self._message(payload)}")
            time.sleep(self.poll_interval)
        raise MVSEPError("mvsep_job_timeout")

    @staticmethod
    def _json(response: requests.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise MVSEPError("mvsep_invalid_json") from exc
        if not isinstance(payload, dict):
            raise MVSEPError("mvsep_response_not_object")
        return payload

    @staticmethod
    def _status(payload: dict[str, Any]) -> str:
        data = payload.get("data")
        if isinstance(data, dict) and data.get("files"):
            return "done"
        if isinstance(data, dict) and data.get("status") is not None:
            return str(data["status"]).strip().lower()
        return str(payload.get("status", "processing")).strip().lower()

    @staticmethod
    def _message(payload: dict[str, Any]) -> str:
        data = payload.get("data")
        if isinstance(data, dict):
            for key in ("message", "error"):
                if data.get(key):
                    return str(data[key])
        for key in ("message", "error"):
            if payload.get(key):
                return str(payload[key])
        return "unknown"

    @classmethod
    def _extract_files(cls, payload: dict[str, Any]) -> dict[str, str]:
        data = payload.get("data")
        if not isinstance(data, dict):
            return {}
        raw_files = data.get("files")
        if isinstance(raw_files, dict):
            extracted: dict[str, str] = {}
            for name, value in raw_files.items():
                if isinstance(value, str) and value:
                    extracted[str(name)] = value
                elif isinstance(value, dict):
                    url = cls._file_url(value)
                    if isinstance(url, str) and url:
                        extracted[str(name)] = url
            return extracted
        if not isinstance(raw_files, list):
            return {}

        extracted: dict[str, str] = {}
        for item in raw_files:
            if isinstance(item, str) and item:
                extracted[Path(item.split("?", 1)[0]).stem] = item
                continue
            if not isinstance(item, dict):
                continue
            name = item.get("name") or item.get("filename") or item.get("stem") or item.get("type")
            url = cls._file_url(item)
            if not name and isinstance(url, str):
                name = Path(url.split("?", 1)[0]).stem
            if name and isinstance(url, str) and url:
                extracted[str(name)] = url
        return extracted

    @staticmethod
    def _file_url(value: dict[str, Any]) -> str | None:
        for key in ("url", "link", "download_url", "download", "file", "path", "href"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate:
                return candidate
        return None

    def _download_stem(self, stem_url: str, output_dir: Path, stem_name: str) -> Path:
        download_url = urljoin(f"{self.base_url}/", stem_url)
        response = self.session.get(download_url, timeout=60)
        response.raise_for_status()
        safe_name = Path(stem_name).name.replace("/", "_")
        suffix = Path(download_url.split("?", 1)[0]).suffix.lower() or ".wav"
        if suffix not in {".wav", ".flac", ".mp3", ".m4a"}:
            suffix = ".wav"
        target = output_dir / f"{safe_name}{suffix}"
        target.write_bytes(response.content)
        return target

    def get_available_models(self) -> Dict[str, str]:
        models = {
            name: f"sep_type={config['sep_type']}"
            for name, config in self.MODELS.items()
        }
        for alias, target in self.MODEL_ALIASES.items():
            models[alias] = models[target]
        return models

    def check_status(self) -> Dict[str, Any]:
        response = self.session.get(
            f"{self.base_url}/app/user",
            params={"api_token": self.api_key},
            timeout=30,
        )
        response.raise_for_status()
        return self._json(response)


class MVSEPModelChain:
    """Compatibility helper for callers that still use the old chain API."""

    def __init__(self, client: Optional[MVSEPClient] = None):
        self.client = client or MVSEPClient()

    def run_vocal_branch(self, vocals_path: Path, output_dir: Path) -> Dict[str, Path]:
        """Compatibility no-op; vocal specialists are not qualified here."""
        return {}

    def run_drum_branch(self, drums_path: Path, output_dir: Path) -> Dict[str, Path]:
        """Run the documented DrumSep model when explicitly requested."""
        try:
            return self.client.separate(drums_path, "DrumSep", output_dir / "drums")
        except (MVSEPError, requests.RequestException):
            return {}

    def run_instrument_branch(self, other_path: Path, output_dir: Path) -> Dict[str, Path]:
        stems: Dict[str, Path] = {}
        for model in (
            "MVSep-Piano",
            "MVSep-Acoustic-Guitar",
            "MVSep-Electric-Guitar",
            "MVSep-Synth",
            "MVSep-Bowed-Strings",
            "MVSep-Wind",
        ):
            try:
                stems.update(self.client.separate(other_path, model, output_dir / model))
            except (MVSEPError, requests.RequestException):
                continue
        return stems
