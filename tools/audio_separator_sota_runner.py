from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess as sp
import sys
import tempfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_AUDIO_SEPARATOR_BIN = ROOT_DIR / ".venvs" / "audio-separator" / "bin" / "audio-separator"
DEFAULT_MODEL_DIR = ROOT_DIR / ".cache" / "audio-separator-models"
TARGET_TO_AUDIO_SEPARATOR_STEM = {
    "piano": "Piano",
    "guitar": "Guitar",
}


def _parse_targets(raw: str) -> list[str]:
    targets = [target.strip().lower() for target in raw.split(",") if target.strip()]
    unsupported = sorted(set(targets) - set(TARGET_TO_AUDIO_SEPARATOR_STEM))
    if unsupported:
        raise SystemExit(f"unsupported target(s): {', '.join(unsupported)}")
    if not targets:
        raise SystemExit("at least one target is required")
    return targets


def _resolve_audio_separator_bin(explicit: str | None) -> Path:
    candidates = [
        explicit,
        os.getenv("AUDIO_SEPARATOR_BIN"),
        str(DEFAULT_AUDIO_SEPARATOR_BIN),
        shutil.which("audio-separator"),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate).expanduser()
        if path.exists():
            return path.resolve()
        path_from_env = shutil.which(candidate)
        if path_from_env:
            return Path(path_from_env).resolve()
    raise FileNotFoundError(
        "audio-separator binary not found. Set AUDIO_SEPARATOR_BIN or install it at "
        f"{DEFAULT_AUDIO_SEPARATOR_BIN}."
    )


def _candidate_outputs(work_dir: Path, stem_name: str) -> list[Path]:
    stem_lower = stem_name.lower()
    files = [
        path
        for path in work_dir.rglob("*")
        if path.is_file()
        and path.suffix.lower() in {".wav", ".flac", ".mp3", ".ogg", ".m4a"}
        and stem_lower in path.stem.lower()
    ]
    return sorted(files, key=lambda path: path.stat().st_mtime, reverse=True)


def _run_one_target(
    audio_separator_bin: Path,
    input_path: Path,
    output_dir: Path,
    *,
    target: str,
    model: str,
    model_file_dir: Path,
    extra_args: list[str],
) -> Path:
    stem_name = TARGET_TO_AUDIO_SEPARATOR_STEM[target]
    with tempfile.TemporaryDirectory(prefix=f"{target}-", dir=output_dir) as work_dir_raw:
        work_dir = Path(work_dir_raw)
        custom_output_names = json.dumps({stem_name: target})
        cmd = [
            str(audio_separator_bin),
            str(input_path),
            "--model_filename",
            model,
            "--output_format",
            "WAV",
            "--output_dir",
            str(work_dir),
            "--model_file_dir",
            str(model_file_dir),
            "--single_stem",
            stem_name,
            "--custom_output_names",
            custom_output_names,
            "--log_level",
            "warning",
        ]
        cmd.extend(extra_args)
        sp.run(cmd, check=True, capture_output=True, text=True)

        exact = work_dir / f"{target}.wav"
        source = exact if exact.exists() else None
        if source is None:
            candidates = _candidate_outputs(work_dir, stem_name)
            if not candidates:
                raise FileNotFoundError(f"audio-separator produced no {stem_name} output in {work_dir}")
            source = candidates[0]

        destination = output_dir / f"{target}.wav"
        shutil.copy2(source, destination)
        return destination.resolve()


def run(
    input_path: Path,
    output_dir: Path,
    *,
    targets: list[str],
    model: str,
    audio_separator_bin: str | None,
    model_file_dir: Path,
    extra_args: list[str],
) -> dict[str, str]:
    input_path = input_path.expanduser().resolve()
    if not input_path.exists():
        raise FileNotFoundError(f"input audio not found: {input_path}")
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    model_file_dir = model_file_dir.expanduser().resolve()
    model_file_dir.mkdir(parents=True, exist_ok=True)
    resolved_bin = _resolve_audio_separator_bin(audio_separator_bin)

    outputs: dict[str, str] = {}
    for target in targets:
        outputs[target] = str(
            _run_one_target(
                resolved_bin,
                input_path,
                output_dir,
                target=target,
                model=model,
                model_file_dir=model_file_dir,
                extra_args=extra_args,
            )
        )
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run audio-separator and normalize specialist instrument outputs for the SOTA adapter."
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--targets", required=True, help="Comma-separated targets, e.g. piano,guitar")
    parser.add_argument("--model", default="htdemucs_6s.yaml")
    parser.add_argument("--audio-separator-bin", default=None)
    parser.add_argument(
        "--model-file-dir",
        type=Path,
        default=Path(os.getenv("AUDIO_SEPARATOR_MODEL_DIR", str(DEFAULT_MODEL_DIR))),
    )
    args = parser.parse_args()

    extra_args = shlex.split(os.getenv("AUDIO_SEPARATOR_EXTRA_ARGS", ""))
    outputs = run(
        args.input,
        args.output,
        targets=_parse_targets(args.targets),
        model=args.model,
        audio_separator_bin=args.audio_separator_bin,
        model_file_dir=args.model_file_dir,
        extra_args=extra_args,
    )
    print(json.dumps({"outputs": outputs}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"audio_separator_sota_runner_failed:{exc}", file=sys.stderr)
        raise SystemExit(1)
