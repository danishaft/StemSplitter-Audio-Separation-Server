from __future__ import annotations

import shutil
from pathlib import Path

from splitter.config import PROFILE_CONFIG
from splitter.separation import build_broad_stems


def separate(input_path: str | Path, output_path: str | Path) -> dict[str, Path]:
    """
    Compatibility helper for the legacy synchronous splitter flow.

    This keeps the original server import path working while delegating
    to the new pipeline code in preview mode.
    """

    source = Path(input_path).resolve()
    target_root = Path(output_path).resolve()
    target_root.mkdir(parents=True, exist_ok=True)

    broad_outputs, _, missing = build_broad_stems(
        source, target_root, "preview", PROFILE_CONFIG["preview"]["run_models"]
    )
    if not broad_outputs:
        raise RuntimeError(f"No stems were created. Missing: {', '.join(missing)}")

    exported: dict[str, Path] = {}
    stems_dir = target_root / "preview_exports"
    stems_dir.mkdir(parents=True, exist_ok=True)
    for stem_name, payload in broad_outputs.items():
        stem_path = Path(str(payload["path"]))
        exported_path = stems_dir / stem_path.name
        if exported_path.resolve() != stem_path.resolve():
            shutil.copy2(stem_path, exported_path)
        exported[stem_name] = exported_path.resolve()
    return exported
