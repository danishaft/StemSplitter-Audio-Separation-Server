from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from splitter.util import ensure_dir  # noqa: E402


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-")
    return slug or "song"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build speech/music/SFX references for a music-only negative control.",
    )
    parser.add_argument("--input", type=Path, required=True, help="Music-only mix.")
    parser.add_argument("--song-name", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--max-seconds", type=float, default=20.0)
    args = parser.parse_args()

    input_path = args.input.expanduser().resolve()
    song_dir = ensure_dir(args.output_root.expanduser().resolve() / _slug(args.song_name))
    audio, sample_rate = librosa.load(input_path, sr=None, mono=False)
    if audio.ndim == 1:
        audio = audio.reshape(1, -1)
    max_samples = int(sample_rate * args.max_seconds)
    music = audio[:, :max_samples].T
    silence = np.zeros_like(music)
    sf.write(song_dir / "music.wav", music, sample_rate, subtype="PCM_16")
    sf.write(song_dir / "speech_dialog.wav", silence, sample_rate, subtype="PCM_16")
    sf.write(song_dir / "sfx.wav", silence, sample_rate, subtype="PCM_16")
    print(f"reference_dir={song_dir}")
    print("stems=music,speech_dialog,sfx")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
