from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
import torch


DEFAULT_REPO = Path(os.getenv("TUSS_REPO", "external_repos/unified-source-separation"))
DEFAULT_CHECKPOINT = Path(
    os.getenv("TUSS_CHECKPOINT", "pretrained_models/tuss.medium.2-4src/checkpoints/model.pth")
)
PROMPTS = ["speech", "sfxbg", "musicbg"]
STEM_MAP = {
    "speech": "speech_dialog",
    "sfxbg": "sfx",
    "musicbg": "music",
}
RESAMPLE_RATE = 48000
_MODEL_CACHE: dict[tuple[str, str], tuple[torch.nn.Module, Any]] = {}


def _validate_file(path: Path, reason: str) -> tuple[bool, str | None]:
    if not path.exists():
        return False, f"{reason}:{path}"
    if path.stat().st_size < 1024:
        return False, f"{reason}_too_small:{path}"
    return True, None


def _validate_repo(repo: Path, checkpoint: Path) -> tuple[bool, str | None]:
    if not repo.exists():
        return False, f"tuss_repo_missing:{repo}"
    valid, reason = _validate_file(repo / "separate.py", "tuss_separate_missing")
    if not valid:
        return False, reason
    valid, reason = _validate_file(repo / "nets" / "model_wrapper.py", "tuss_model_wrapper_missing")
    if not valid:
        return False, reason
    valid, reason = _validate_file(checkpoint, "tuss_checkpoint_missing")
    if not valid:
        return False, reason
    hparams = checkpoint.parent.parent / "hparams.yaml"
    valid, reason = _validate_file(hparams, "tuss_hparams_missing")
    if not valid:
        return False, reason
    return True, None


def _load_model(repo: Path, checkpoint: Path, device: torch.device) -> tuple[torch.nn.Module, Any]:
    cache_key = (str(checkpoint), str(device))
    if cache_key in _MODEL_CACHE:
        return _MODEL_CACHE[cache_key]

    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))

    from nets.model_wrapper import SeparationModel  # type: ignore
    from utils.average_model_params import average_model_params  # type: ignore
    from utils.config import yaml_to_parser  # type: ignore

    hparams = yaml_to_parser(checkpoint.parent.parent / "hparams.yaml").parse_args([])
    model = SeparationModel(
        hparams.encoder_name,
        hparams.encoder_conf,
        hparams.decoder_name,
        hparams.decoder_conf,
        hparams.model_name,
        hparams.model_conf,
        hparams.css_conf,
        hparams.variance_normalization,
    )
    state_dict = average_model_params([checkpoint])
    model.load_state_dict({key.replace("model.", ""): value for key, value in state_dict.items()})
    model.to(device)
    model.eval()
    _MODEL_CACHE[cache_key] = (model, hparams)
    return model, hparams


def _resample(audio: torch.Tensor, sample_rate: int, target_rate: int) -> torch.Tensor:
    if sample_rate == target_rate:
        return audio
    from torchaudio.functional import resample

    return resample(audio, sample_rate, target_rate)


def _run_channel(
    model: torch.nn.Module,
    mono: torch.Tensor,
    *,
    sample_rate: int,
    device: torch.device,
    css_segment_size: int | None,
    css_shift_size: int | None,
) -> torch.Tensor:
    model_input = _resample(mono.to(device), sample_rate, RESAMPLE_RATE)
    with torch.inference_mode():
        if css_segment_size is not None:
            model.css_segment_size = css_segment_size
            model.css_shift_size = css_shift_size or max(1, css_segment_size // 2)
            output, *_ = model.css(model_input, [PROMPTS])
        else:
            output, *_ = model(model_input, [PROMPTS])
    output = _resample(output.cpu(), RESAMPLE_RATE, sample_rate)
    return output


def run_tuss(
    input_path: Path,
    output_dir: Path,
    *,
    repo: Path = DEFAULT_REPO,
    checkpoint: Path | None = None,
    device: str = "cpu",
    css_segment_size: int | None = 8,
    css_shift_size: int | None = 4,
) -> dict[str, Any]:
    repo = repo.resolve()
    input_path = input_path.resolve()
    output_dir = output_dir.resolve()
    checkpoint_path = (repo / (checkpoint or DEFAULT_CHECKPOINT)).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    valid, reason = _validate_repo(repo, checkpoint_path)
    if not valid:
        return {"status": "skipped", "reason": reason, "artifacts": {}}

    requested_device = device
    if requested_device == "cuda" and not torch.cuda.is_available():
        requested_device = "cpu"
    torch_device = torch.device(requested_device)

    try:
        audio, sample_rate = sf.read(input_path, always_2d=True, dtype="float32")
        model, _ = _load_model(repo, checkpoint_path, torch_device)
        channels = []
        for channel_index in range(audio.shape[1]):
            mono = torch.from_numpy(audio[:, channel_index]).unsqueeze(0)
            channels.append(
                _run_channel(
                    model,
                    mono,
                    sample_rate=int(sample_rate),
                    device=torch_device,
                    css_segment_size=css_segment_size,
                    css_shift_size=css_shift_size,
                )
            )
    except Exception as exc:
        return {
            "status": "error",
            "reason": f"tuss_inference_failed:{type(exc).__name__}:{exc}",
            "artifacts": {},
        }

    min_length = min(channel_output.shape[-1] for channel_output in channels)
    stacked = torch.stack([channel_output[:, :min_length] for channel_output in channels], dim=-1)
    scale = max(float(np.max(np.abs(audio))) / 0.95, 1.0)
    artifacts: dict[str, str] = {}
    for prompt_index, prompt in enumerate(PROMPTS):
        target_name = STEM_MAP[prompt]
        stem_audio = (stacked[prompt_index].numpy() / scale).astype(np.float32)
        target = output_dir / f"{target_name}.wav"
        sf.write(target, stem_audio, int(sample_rate), subtype="PCM_16")
        artifacts[target_name] = str(target)

    return {
        "status": "completed",
        "reason": None,
        "artifacts": artifacts,
        "sample_rate": int(sample_rate),
        "channels": int(audio.shape[1]),
        "device": str(torch_device),
        "prompts": PROMPTS,
        "checkpoint": str(checkpoint_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run TUSS speech/music/SFX separation.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--repo", type=Path, default=DEFAULT_REPO)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--device", default="cpu", choices=["cpu", "cuda"])
    parser.add_argument("--css-segment-size", type=int, default=8)
    parser.add_argument("--css-shift-size", type=int, default=4)
    args = parser.parse_args()

    result = run_tuss(
        args.input,
        args.out_dir,
        repo=args.repo,
        checkpoint=args.checkpoint,
        device=args.device,
        css_segment_size=args.css_segment_size,
        css_shift_size=args.css_shift_size,
    )
    manifest_path = args.out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
