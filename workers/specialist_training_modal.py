from __future__ import annotations

import csv
import hashlib
import json
import os
import pickle
import re
import shutil
import subprocess
import sys
import tarfile
import time
import zipfile
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path("/root/project")
try:
    REMOTE_PROJECT_AVAILABLE = PROJECT_ROOT.is_dir()
except OSError:
    REMOTE_PROJECT_AVAILABLE = False
if REMOTE_PROJECT_AVAILABLE:
    sys.path.insert(0, str(PROJECT_ROOT))

from splitter.specialist_training_contract import (  # noqa: E402
    SPECIALIST_BASE_IDS,
    legacy_validation_group,
)

try:
    import modal
except ImportError:  # pragma: no cover - Modal is a deployment dependency
    modal = None
    app = None
else:
    app = modal.App("stemsplitter-specialist-training")
    training_volume = modal.Volume.from_name(
        "stemsplitter-specialist-training",
        create_if_missing=True,
    )
    image = (
        modal.Image.debian_slim(python_version="3.11")
        .apt_install("ffmpeg", "libsndfile1")
        .pip_install(
            "auraloss",
            "audiomentations==0.24.0",
            "beartype==0.14.1",
            "einops==0.8.1",
            "librosa",
            "ml-collections==1.1.0",
            "numpy<2.0",
            "omegaconf==2.2.3",
            "packaging",
            "pandas",
            "pedalboard~=0.8.1",
            "prodigyopt",
            "pyyaml",
            "rotary-embedding-torch==0.3.5",
            "scipy",
            "soundfile",
            "torch==2.10.0",
            "torchaudio==2.10.0",
            "torchmetrics==0.11.4",
            "tqdm",
            "wandb",
        )
        .pip_install(
            "matplotlib",
            "boto3>=1.35.0",
            "huggingface-hub>=1.0.0",
            "requests>=2.31.0",
            "torch_l1_snr>=0.1.2",
            "torch_log_wmse>=0.3.1",
        )
        .add_local_dir(
            "external_repos/Music-Source-Separation-Training",
            remote_path="/root/msst",
        )
        .add_local_dir("splitter", remote_path="/root/project/splitter")
        .add_local_dir(
            "datasets/registry",
            remote_path="/root/project/datasets/registry",
        )
        .add_local_dir(
            "datasets/inventories",
            remote_path="/root/project/datasets/inventories",
        )
        .add_local_dir(
            "datasets/manifests/selections",
            remote_path="/root/project/datasets/manifests/selections",
        )
        .add_local_dir(
            "datasets/manifests/acquisition",
            remote_path="/root/project/datasets/manifests/acquisition",
        )
        .add_local_dir(
            "datasets/manifests/curation",
            remote_path="/root/project/datasets/manifests/curation",
        )
        .add_local_dir(
            "datasets/manifests/items",
            remote_path="/root/project/datasets/manifests/items",
        )
        .add_local_dir(
            "datasets/corpora",
            remote_path="/root/project/datasets/corpora",
        )
        .add_local_file(
            "training/__init__.py",
            remote_path="/root/project/training/__init__.py",
        )
        .add_local_file(
            "training/audio_recipes.py",
            remote_path="/root/project/training/audio_recipes.py",
        )
        .add_local_file(
            "training/manifests.py",
            remote_path="/root/project/training/manifests.py",
        )
        .add_local_file(
            "training/base_specs.yaml",
            remote_path="/root/project/training/base_specs.yaml",
        )
        .add_local_file(
            "models/bsroformer_synth_xlance_candidate.yaml",
            remote_path=(
                "/root/project/models/"
                "bsroformer_synth_xlance_candidate.yaml"
            ),
        )
        .add_local_file(
            "scripts/build_training_manifest.py",
            remote_path="/root/project/scripts/build_training_manifest.py",
        )
        .add_local_file(
            "scripts/build_specialist_validation_set.py",
            remote_path=(
                "/root/project/scripts/"
                "build_specialist_validation_set.py"
            ),
        )
    )


TRAINING_ROOT = Path("/training")
BASE_IDS = set(SPECIALIST_BASE_IDS)
DATASET_FAMILIES = {
    "acoustic_guitar",
    "electric_guitar",
    "strings",
    "synth",
    "wind_brass",
}
DATASET_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validation_root(base_id: str, validation_set_id: str) -> Path:
    if validation_set_id:
        return TRAINING_ROOT / "validation_sets" / validation_set_id / base_id
    validation_group = legacy_validation_group(base_id)
    if validation_group is None:
        raise ValueError(
            f"validation_set_id is required for specialist base {base_id}"
        )
    return (
        TRAINING_ROOT
        / "datasets/sprint-clean-v1/research_all"
        / validation_group
        / "stage_25/validation"
    )


def _safe_archive_destination(root: Path, member_name: str) -> Path:
    member = Path(member_name)
    if member.is_absolute() or ".." in member.parts:
        raise ValueError(f"unsafe archive member: {member_name}")
    destination = (root / member).resolve()
    if root.resolve() not in destination.parents and destination != root.resolve():
        raise ValueError(f"archive member escapes destination: {member_name}")
    return destination


def _extract_archive(source: Path, destination: Path) -> int:
    destination.mkdir(parents=True, exist_ok=True)
    extracted = 0
    if source.suffix.lower() == ".zip":
        with zipfile.ZipFile(source) as archive:
            for member in archive.infolist():
                target = _safe_archive_destination(destination, member.filename)
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as incoming, target.open("wb") as output:
                    shutil.copyfileobj(incoming, output, length=8 * 1024 * 1024)
                extracted += 1
    elif source.name.endswith((".tar.gz", ".tar.bz2")):
        with tarfile.open(source, "r:*") as archive:
            for member in archive:
                if not member.isfile():
                    continue
                target = _safe_archive_destination(destination, member.name)
                target.parent.mkdir(parents=True, exist_ok=True)
                incoming = archive.extractfile(member)
                if incoming is None:
                    continue
                with incoming, target.open("wb") as output:
                    shutil.copyfileobj(incoming, output, length=8 * 1024 * 1024)
                extracted += 1
    else:
        raise ValueError(f"unsupported training archive: {source}")
    return extracted


def _assert_index_materialized(index_path: Path) -> int:
    missing: list[str] = []
    row_count = 0
    with index_path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            row_count += 1
            path = Path(str(row["path"]))
            if not path.is_file() and len(missing) < 20:
                missing.append(str(path))
    if missing:
        raise FileNotFoundError(
            "training index contains unavailable audio: " + ", ".join(missing)
        )
    return row_count


if modal is not None:

    @app.function(
        image=image,
        cpu=8,
        memory=32768,
        timeout=21600,
        volumes={str(TRAINING_ROOT): training_volume},
    )
    def prepare_source_archives() -> dict[str, Any]:
        sys.path.insert(0, "/root/project")
        from splitter.training_data_acquisition import (
            acquire_remote_zip_manifest,
            acquire_remote_zip_selection,
            acquire_source_file,
        )

        staging_root = TRAINING_ROOT / "source_audio/datasets/staging"
        receipt_root = TRAINING_ROOT / "source_receipts"
        reports = []

        raw_target, raw_receipt = acquire_remote_zip_manifest(
            Path(
                "/root/project/datasets/manifests/selections/"
                "rawstems-curated-specialists-v1.json"
            ),
            staging_root=staging_root,
            receipt_root=receipt_root,
        )
        reports.append(
            {
                "source_id": "rawstems",
                "destination": str(raw_target),
                "entry_count": raw_receipt["entry_count"],
            }
        )
        training_volume.commit()

        for source_id, receipt_path in (
            (
                "albumdb",
                "/root/project/datasets/manifests/acquisition/albumdb/"
                "zenodo-19683000/raw-stems.selection.json",
            ),
            (
                "eg_ipt",
                "/root/project/datasets/manifests/acquisition/eg_ipt/"
                "zenodo-15205644/dyn-close-mic.selection.json",
            ),
        ):
            selection = json.loads(
                Path(receipt_path).read_text(encoding="utf-8")
            )
            target, receipt = acquire_remote_zip_selection(
                source_id,
                str(selection["provider_path"]),
                str(selection["selection_name"]),
                include_components=tuple(selection["include_components"]),
                suffixes=tuple(selection["suffixes"]),
                staging_root=staging_root,
                receipt_root=receipt_root,
            )
            reports.append(
                {
                    "source_id": source_id,
                    "destination": str(target),
                    "entry_count": receipt["entry_count"],
                }
            )
            training_volume.commit()

        bundles = (
            (
                "cocochorales",
                "full-v1-train-shards-1-25",
                "bounded-main-train-v1",
                (
                    "datasets/cocochorales/cocochorales_full_v1_zipped/"
                    "main_dataset/train/1.tar.bz2",
                    "datasets/cocochorales/cocochorales_full_v1_zipped/"
                    "main_dataset/train/25.tar.bz2",
                ),
                False,
            ),
            (
                "medleydb_sample",
                "zenodo-1438309",
                "audio-only-v1",
                ("MedleyDB_Sample.tar.gz",),
                False,
            ),
            (
                "spheres",
                "zenodo-17347681",
                "stereo-mix-audio-v1",
                ("TheSpheresDataset-StereoMix.zip",),
                False,
            ),
            (
                "urmp",
                "zenodo-5034983",
                "audio-only-v1",
                ("Dataset.tar.gz",),
                True,
            ),
        )
        for source_id, version, selection_name, provider_paths, transcode in bundles:
            destination = (
                staging_root
                / source_id
                / version
                / "selections"
                / selection_name
            )
            marker = destination / ".modal-materialization.json"
            if marker.is_file():
                reports.append(json.loads(marker.read_text(encoding="utf-8")))
                continue
            extracted_count = 0
            for provider_path in provider_paths:
                archive, _receipt = acquire_source_file(
                    source_id,
                    provider_path,
                    staging_root=staging_root,
                    receipt_root=receipt_root,
                )
                if archive is None:
                    raise FileNotFoundError(provider_path)
                extracted_count += _extract_archive(archive, destination)
                archive.unlink()
            if transcode:
                for wav in destination.rglob("*.wav"):
                    if wav.name.startswith("._"):
                        wav.unlink()
                        continue
                    flac = wav.with_suffix(".flac")
                    completed = subprocess.run(
                        [
                            "ffmpeg",
                            "-nostdin",
                            "-v",
                            "error",
                            "-i",
                            str(wav),
                            "-compression_level",
                            "8",
                            str(flac),
                        ],
                        check=False,
                    )
                    if completed.returncode != 0:
                        raise RuntimeError(f"failed to transcode {wav}")
                    wav.unlink()
            report = {
                "source_id": source_id,
                "destination": str(destination),
                "extracted_file_count": extracted_count,
            }
            marker.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            reports.append(report)
            training_volume.commit()

        archives = {
            "chorale_bricks": (
                "zenodo-15081741",
                ("01_AudioAndAnnotations.zip",),
            ),
            "guitar_techs": (
                "zenodo-14963133",
                (
                    "P1_chords.zip",
                    "P1_scales.zip",
                    "P1_singlenotes.zip",
                    "P1_techniques.zip",
                    "P2_chords.zip",
                    "P2_scales.zip",
                    "P2_singlenotes.zip",
                    "P2_techniques.zip",
                    "P3_music.zip",
                ),
            ),
            "quartset": ("zenodo-15708701", ("QuartSet.zip",)),
            "tinysol": ("zenodo-3659365", ("TinySOL.tar.gz",)),
        }
        for source_id, (version, provider_paths) in archives.items():
            for provider_path in provider_paths:
                extracted_name = provider_path.replace(".", "-")
                destination = (
                    TRAINING_ROOT
                    / "source_audio/datasets/extracted"
                    / source_id
                    / version
                    / extracted_name
                )
                marker = destination / ".modal-extraction.json"
                if marker.is_file():
                    reports.append(json.loads(marker.read_text(encoding="utf-8")))
                    continue
                archive, _receipt = acquire_source_file(
                    source_id,
                    provider_path,
                    staging_root=staging_root,
                    receipt_root=receipt_root,
                )
                if archive is None:
                    raise FileNotFoundError(provider_path)
                extracted_count = _extract_archive(archive, destination)
                archive.unlink()
                report = {
                    "source_id": source_id,
                    "source": provider_path,
                    "destination": str(destination),
                    "extracted_file_count": extracted_count,
                }
                marker.write_text(
                    json.dumps(report, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                reports.append(report)
                training_volume.commit()

        return {"archives": reports}

    @app.function(
        image=image,
        cpu=16,
        memory=32768,
        timeout=21600,
        volumes={str(TRAINING_ROOT): training_volume},
    )
    def audit_rawstems_selection() -> dict[str, Any]:
        sys.path.insert(0, "/root/project")
        from splitter.training_corpus import audit_training_tree, file_checksum

        version = "current-pinned-at-acquisition"
        selection_name = "rawstems-curated-specialists-v1"
        receipt_path = (
            TRAINING_ROOT
            / "source_receipts"
            / "rawstems"
            / version
            / f"{selection_name}.selection.json"
        )
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        output_dir = (
            TRAINING_ROOT
            / "source_items"
            / "rawstems"
            / version
            / selection_name
        )
        report = audit_training_tree(
            "rawstems",
            Path(str(receipt["local_path"])),
            output_dir=output_dir,
            provenance_sha256=file_checksum(receipt_path),
            split_assignments=receipt["song_split_assignments"],
        )
        training_volume.commit()
        return report

    @app.function(
        image=image,
        cpu=4,
        memory=8192,
        timeout=21600,
        volumes={str(TRAINING_ROOT): training_volume},
    )
    def acquire_huggingface_prefix(
        source_id: str,
        provider_prefix: str,
        suffix: str,
    ) -> dict[str, Any]:
        sys.path.insert(0, "/root/project")
        from huggingface_hub import hf_hub_download

        from splitter.training_data_acquisition import list_source_files

        source, provider_files = list_source_files(source_id)
        acquisition = source.raw.get("acquisition") or {}
        if acquisition.get("provider") != "huggingface":
            raise ValueError(f"{source_id} is not a Hugging Face source")

        selected = [
            item
            for item in provider_files
            if item.path.startswith(provider_prefix)
            and item.path.lower().endswith(suffix.lower())
        ]
        if not selected:
            raise ValueError(
                f"no {source_id} files match {provider_prefix!r} and {suffix!r}"
            )

        destination = (
            TRAINING_ROOT
            / "source_audio"
            / "datasets"
            / "staging"
            / source.source_id
            / source.version
        )
        destination.mkdir(parents=True, exist_ok=True)
        downloaded = 0
        reused = 0
        for index, provider_file in enumerate(selected, start=1):
            target = destination / provider_file.path
            if (
                target.is_file()
                and (
                    not provider_file.size_bytes
                    or target.stat().st_size == provider_file.size_bytes
                )
            ):
                reused += 1
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            hf_hub_download(
                repo_id=str(acquisition["repo_id"]),
                filename=provider_file.path,
                repo_type=str(acquisition.get("repo_type") or "dataset"),
                revision=provider_file.provider_revision,
                token=os.getenv("HF_TOKEN") or None,
                local_dir=destination,
            )
            if (
                provider_file.size_bytes
                and target.stat().st_size != provider_file.size_bytes
            ):
                raise RuntimeError(f"download size mismatch: {provider_file.path}")
            downloaded += 1
            if index % 25 == 0:
                training_volume.commit()

        receipt = {
            "schema_version": "1.0",
            "source_id": source.source_id,
            "source_version": source.version,
            "provider": "huggingface",
            "repo_id": acquisition["repo_id"],
            "provider_prefix": provider_prefix,
            "suffix": suffix,
            "selected_file_count": len(selected),
            "selected_size_bytes": sum(item.size_bytes for item in selected),
            "downloaded_file_count": downloaded,
            "reused_file_count": reused,
            "destination": str(destination),
            "provider_revision": selected[0].provider_revision,
        }
        receipt_path = (
            TRAINING_ROOT
            / "source_receipts"
            / source.source_id
            / source.version
            / "prefix-acquisition.json"
        )
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        training_volume.commit()
        return receipt

    @app.function(
        image=image,
        cpu=4,
        memory=8192,
        timeout=21600,
        volumes={str(TRAINING_ROOT): training_volume},
    )
    def acquire_registered_file(
        source_id: str,
        provider_path: str,
    ) -> dict[str, Any]:
        sys.path.insert(0, "/root/project")
        from splitter.training_data_acquisition import acquire_source_file

        local_path, receipt = acquire_source_file(
            source_id,
            provider_path,
            staging_root=TRAINING_ROOT / "source_audio/datasets/staging",
            receipt_root=TRAINING_ROOT / "source_receipts",
        )
        training_volume.commit()
        return {
            "source_id": source_id,
            "provider_path": provider_path,
            "local_path": str(local_path) if local_path else None,
            "size_bytes": receipt["size_bytes"],
            "sha256": receipt["sha256"],
            "reused": receipt.get("reused", False),
        }

    @app.function(
        image=image,
        cpu=16,
        memory=32768,
        timeout=21600,
        volumes={str(TRAINING_ROOT): training_volume},
    )
    def audit_registered_tree(
        source_id: str,
        source_subpath: str,
        release_name: str,
    ) -> dict[str, Any]:
        sys.path.insert(0, "/root/project")
        from splitter.training_corpus import audit_training_tree, file_checksum
        from splitter.training_data_registry import load_training_data_registry

        relative = Path(source_subpath)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("source_subpath must be a safe relative path")
        if not DATASET_ID_PATTERN.fullmatch(release_name):
            raise ValueError("invalid release_name")

        source = load_training_data_registry().sources.get(source_id)
        if source is None:
            raise ValueError(f"unknown training source: {source_id}")
        source_root = (
            TRAINING_ROOT
            / "source_audio"
            / "datasets"
            / "staging"
            / source.source_id
            / source.version
            / relative
        )
        receipt_path = (
            TRAINING_ROOT
            / "source_receipts"
            / source.source_id
            / source.version
            / "prefix-acquisition.json"
        )
        if not receipt_path.is_file():
            raise FileNotFoundError(str(receipt_path))
        output_dir = (
            TRAINING_ROOT
            / "source_items"
            / source.source_id
            / source.version
            / release_name
        )
        report = audit_training_tree(
            source.source_id,
            source_root,
            output_dir=output_dir,
            provenance_sha256=file_checksum(receipt_path),
        )
        training_volume.commit()
        return report

    @app.function(
        image=image,
        cpu=8,
        memory=16384,
        timeout=21600,
        volumes={str(TRAINING_ROOT): training_volume},
    )
    def extract_registered_archive(
        source_id: str,
        provider_path: str,
        release_name: str,
    ) -> dict[str, Any]:
        sys.path.insert(0, "/root/project")
        from splitter.training_data_registry import load_training_data_registry

        relative_provider_path = Path(provider_path)
        if (
            relative_provider_path.is_absolute()
            or ".." in relative_provider_path.parts
        ):
            raise ValueError("provider_path must be a safe relative path")
        if not DATASET_ID_PATTERN.fullmatch(release_name):
            raise ValueError("invalid release_name")
        source = load_training_data_registry().sources.get(source_id)
        if source is None:
            raise ValueError(f"unknown training source: {source_id}")

        archive = (
            TRAINING_ROOT
            / "source_audio"
            / "datasets"
            / "staging"
            / source.source_id
            / source.version
            / relative_provider_path
        )
        destination = (
            TRAINING_ROOT
            / "source_audio"
            / "datasets"
            / "extracted"
            / source.source_id
            / source.version
            / release_name
        )
        marker = destination / ".modal-extraction.json"
        if marker.is_file():
            return json.loads(marker.read_text(encoding="utf-8"))
        extracted_count = _extract_archive(archive, destination)
        report = {
            "schema_version": "1.0",
            "source_id": source.source_id,
            "source_version": source.version,
            "provider_path": provider_path,
            "release_name": release_name,
            "archive_sha256": _sha256(archive),
            "extracted_file_count": extracted_count,
            "destination": str(destination),
        }
        marker.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        training_volume.commit()
        return report

    @app.function(
        image=image,
        cpu=16,
        memory=32768,
        timeout=21600,
        volumes={str(TRAINING_ROOT): training_volume},
    )
    def curate_fsl10k() -> dict[str, Any]:
        sys.path.insert(0, "/root/project")
        from collections import defaultdict

        from splitter.training_corpus import audit_training_tree, file_checksum

        source_root = (
            TRAINING_ROOT
            / "source_audio/datasets/extracted/freesound_loop_dataset"
            / "zenodo-3967852/fsl10k-v1"
        )
        annotation_archive = (
            TRAINING_ROOT
            / "source_audio/datasets/staging/freesound_loop_dataset"
            / "zenodo-3967852/annotations.zip"
        )
        metadata = json.loads(
            (source_root / "metadata.json").read_text(encoding="utf-8")
        )
        annotations: dict[str, list[dict[str, Any]]] = defaultdict(list)
        with zipfile.ZipFile(annotation_archive) as archive:
            for member in archive.infolist():
                stem = Path(member.filename).stem
                if member.is_dir() or not stem.startswith("sound-"):
                    continue
                sound_id = stem.partition("-")[2]
                annotations[sound_id].append(
                    json.loads(archive.read(member).decode("utf-8"))
                )

        patterns = {
            "acoustic_guitar": re.compile(
                r"\b(acoustic guitar|classical guitar|nylon(?: string)? guitar"
                r"|spanish guitar)\b"
            ),
            "electric_guitar": re.compile(
                r"\b(electric guitar|distorted electric guitar)\b"
            ),
            "synth": re.compile(
                r"\b(synth|synthesizer|synthesis|synthwave|arpeggiator"
                r"|synth pad|synth lead)\b"
            ),
            "strings": re.compile(
                r"\b(violin|viola|cello|violoncello|string quartet"
                r"|string ensemble|orchestral strings)\b"
            ),
            "wind_brass": re.compile(
                r"\b(trumpet|trombone|french horn|tuba|sax|saxophone"
                r"|flute|clarinet|oboe|bassoon|woodwind|brass section)\b"
            ),
        }
        audio_by_id = {
            path.name.partition("_")[0]: path
            for path in (source_root / "audio" / "wav").glob("*.wav")
        }
        selection_name = "fsl10k-expert-specialists-v1"
        selection_root = (
            TRAINING_ROOT
            / "source_audio/datasets/staging/freesound_loop_dataset"
            / "zenodo-3967852/selections"
            / selection_name
        )
        selected: list[dict[str, Any]] = []
        for sound_id, item in metadata.items():
            text = " ".join(
                str(value or "")
                for value in (
                    item.get("name"),
                    item.get("description"),
                    item.get("pack_name"),
                    " ".join(item.get("tags") or []),
                )
            ).lower()
            families = [
                family
                for family, pattern in patterns.items()
                if pattern.search(text)
            ]
            votes = annotations.get(str(sound_id), [])
            if len(families) != 1 or not votes:
                continue
            clean_votes = []
            for vote in votes:
                instruments = vote.get("instrumentation") or {}
                clean_votes.append(
                    not vote.get("discard")
                    and vote.get("well_cut") is True
                    and not any(
                        instruments.get(label)
                        for label in ("percussion", "vocal", "fx", "bass")
                    )
                    and any(
                        instruments.get(label)
                        for label in ("melody", "chords")
                    )
                )
            if not all(clean_votes):
                continue
            source_path = audio_by_id.get(str(sound_id))
            if source_path is None:
                continue
            family = families[0]
            target = selection_root / family / source_path.name
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                shutil.copy2(source_path, target)
            selected.append(
                {
                    "sound_id": str(sound_id),
                    "family": family,
                    "license": item.get("license"),
                    "name": item.get("name"),
                    "annotation_count": len(votes),
                    "relative_path": str(target.relative_to(selection_root)),
                }
            )

        curation_path = (
            TRAINING_ROOT
            / "source_receipts/freesound_loop_dataset/zenodo-3967852"
            / f"{selection_name}.json"
        )
        curation_path.parent.mkdir(parents=True, exist_ok=True)
        curation_path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "source_id": "freesound_loop_dataset",
                    "selection_name": selection_name,
                    "method": "strict_text_plus_unanimous_expert_annotation",
                    "selected_file_count": len(selected),
                    "items": selected,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        output_dir = (
            TRAINING_ROOT
            / "source_items/freesound_loop_dataset/zenodo-3967852"
            / selection_name
        )
        report = audit_training_tree(
            "freesound_loop_dataset",
            selection_root,
            output_dir=output_dir,
            provenance_sha256=file_checksum(curation_path),
        )
        report["curation_selected_file_count"] = len(selected)
        training_volume.commit()
        return report

    @app.function(
        image=image,
        cpu=16,
        memory=32768,
        timeout=21600,
        volumes={str(TRAINING_ROOT): training_volume},
    )
    def curate_nsynth() -> dict[str, Any]:
        sys.path.insert(0, "/root/project")
        from collections import Counter

        from splitter.training_corpus import audit_training_tree, file_checksum

        source_root = (
            TRAINING_ROOT
            / "source_audio/datasets/extracted/nsynth"
            / "magenta-2017-04-10/train/nsynth-train"
        )
        examples_path = source_root / "examples.json"
        audio_root = source_root / "audio"
        if not examples_path.is_file() or not audio_root.is_dir():
            raise FileNotFoundError("extracted NSynth train data is incomplete")

        selection_name = "strict-specialist-notes-v1"
        family_counts: Counter[str] = Counter()
        family_assignments: dict[str, str] = {}
        examples = json.loads(examples_path.read_text(encoding="utf-8"))
        for note_id, item in examples.items():
            instrument_family = str(item["instrument_family_str"])
            instrument_source = str(item["instrument_source_str"])
            family: str | None = None
            if instrument_family == "guitar" and instrument_source == "acoustic":
                family = "acoustic_guitar"
            elif (
                instrument_family == "guitar"
                and instrument_source == "electronic"
            ):
                family = "electric_guitar"
            elif instrument_family == "synth_lead":
                family = "synth"
            elif (
                instrument_family == "string"
                and instrument_source == "acoustic"
            ):
                family = "strings"
            elif (
                instrument_family in {"brass", "flute", "reed"}
                and instrument_source == "acoustic"
            ):
                family = "wind_brass"
            if family is None:
                continue

            source_path = audio_root / f"{note_id}.wav"
            if not source_path.is_file():
                raise FileNotFoundError(source_path)
            relative_path = source_path.relative_to(source_root).as_posix()
            family_assignments[relative_path] = family
            family_counts[family] += 1

        curation_path = (
            TRAINING_ROOT
            / "source_receipts/nsynth/magenta-2017-04-10"
            / f"{selection_name}.json"
        )
        curation_path.parent.mkdir(parents=True, exist_ok=True)
        curation_path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "source_id": "nsynth",
                    "selection_name": selection_name,
                    "method": "authoritative_family_and_source_labels",
                    "family_counts": dict(sorted(family_counts.items())),
                    "selected_file_count": sum(family_counts.values()),
                    "excluded_policy": (
                        "exclude synthetic imitations and ambiguous keyboard/"
                        "organ families from specialist targets"
                    ),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        output_dir = (
            TRAINING_ROOT
            / "source_items/nsynth/magenta-2017-04-10"
            / selection_name
        )
        report = audit_training_tree(
            "nsynth",
            source_root,
            output_dir=output_dir,
            provenance_sha256=file_checksum(curation_path),
            selected_paths=set(family_assignments),
            family_assignments=family_assignments,
        )
        report["curation_family_counts"] = dict(sorted(family_counts.items()))
        training_volume.commit()
        return report

    @app.function(
        image=image,
        cpu=4,
        memory=8192,
        timeout=21600,
        volumes={str(TRAINING_ROOT): training_volume},
    )
    def prune_nsynth_unselected() -> dict[str, Any]:
        audio_root = (
            TRAINING_ROOT
            / "source_audio/datasets/extracted/nsynth"
            / "magenta-2017-04-10/train/nsynth-train/audio"
        )
        manifest_path = (
            TRAINING_ROOT
            / "source_items/nsynth/magenta-2017-04-10"
            / "strict-specialist-notes-v1/items.jsonl"
        )
        if not manifest_path.is_file():
            raise FileNotFoundError(manifest_path)

        retained = {
            Path(row["local_path"]).resolve()
            for line in manifest_path.read_text(encoding="utf-8").splitlines()
            if (row := json.loads(line)).get("accepted") is True
        }
        if not retained:
            raise RuntimeError("refusing to prune NSynth with an empty manifest")

        deleted_count = 0
        retained_count = 0
        for source_path in audio_root.glob("*.wav"):
            if source_path.resolve() in retained:
                retained_count += 1
            else:
                source_path.unlink()
                deleted_count += 1
        if retained_count != len(retained):
            raise RuntimeError(
                f"retained NSynth count mismatch: {retained_count}/{len(retained)}"
            )
        training_volume.commit()
        return {
            "retained_file_count": retained_count,
            "deleted_file_count": deleted_count,
        }

    @app.function(
        image=image,
        cpu=8,
        memory=16384,
        timeout=21600,
        volumes={str(TRAINING_ROOT): training_volume},
    )
    def curate_idmt_smt_guitar() -> dict[str, Any]:
        sys.path.insert(0, "/root/project")
        from collections import Counter

        from splitter.training_corpus import audit_training_tree, file_checksum

        source_root = (
            TRAINING_ROOT
            / "source_audio/datasets/extracted/idmt_smt_guitar"
            / "zenodo-7544110/v2/IDMT-SMT-GUITAR_V2"
        )
        selection_name = "independent-guitar-recordings-v1"
        source_groups = (
            ("electric_guitar", source_root / "dataset1"),
            ("electric_guitar", source_root / "dataset2/audio"),
            ("electric_guitar", source_root / "dataset3/audio"),
            ("electric_guitar", source_root / "dataset4/Career SG"),
            ("electric_guitar", source_root / "dataset4/Ibanez 2820"),
            ("acoustic_guitar", source_root / "dataset4/acoustic_mic"),
        )
        family_counts: Counter[str] = Counter()
        family_assignments: dict[str, str] = {}
        for family, group_root in source_groups:
            if not group_root.is_dir():
                raise FileNotFoundError(group_root)
            for source_path in sorted(group_root.rglob("*.wav")):
                relative = source_path.relative_to(source_root)
                family_assignments[relative.as_posix()] = family
                family_counts[family] += 1

        curation_path = (
            TRAINING_ROOT
            / "source_receipts/idmt_smt_guitar/zenodo-7544110"
            / f"{selection_name}.json"
        )
        curation_path.parent.mkdir(parents=True, exist_ok=True)
        curation_path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "source_id": "idmt_smt_guitar",
                    "selection_name": selection_name,
                    "method": "official_session_instrument_mapping",
                    "family_counts": dict(sorted(family_counts.items())),
                    "selected_file_count": sum(family_counts.values()),
                    "excluded_policy": (
                        "exclude acoustic_pickup because it is synchronized "
                        "with the retained acoustic_mic performance"
                    ),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        output_dir = (
            TRAINING_ROOT
            / "source_items/idmt_smt_guitar/zenodo-7544110"
            / selection_name
        )
        report = audit_training_tree(
            "idmt_smt_guitar",
            source_root,
            output_dir=output_dir,
            provenance_sha256=file_checksum(curation_path),
            selected_paths=set(family_assignments),
            family_assignments=family_assignments,
        )
        report["curation_family_counts"] = dict(sorted(family_counts.items()))
        training_volume.commit()
        return report

    @app.function(
        image=image,
        cpu=8,
        memory=16384,
        timeout=21600,
        volumes={str(TRAINING_ROOT): training_volume},
    )
    def curate_onair_music() -> dict[str, Any]:
        sys.path.insert(0, "/root/project")
        from splitter.training_corpus import audit_training_tree, file_checksum

        source_root = (
            TRAINING_ROOT
            / "source_audio/datasets/extracted/onair_music/v4-1cdaae8"
        )
        selection_name = "explicit-wind-brass-v1"
        family_assignments: dict[str, str] = {}
        for source_path in sorted(source_root.rglob("*.wav")):
            label = source_path.stem.lower()
            if any(token in label for token in ("horns", "trumps", "sax")):
                relative = source_path.relative_to(source_root).as_posix()
                family_assignments[relative] = "wind_brass"
        if not family_assignments:
            raise RuntimeError("OnAir contains no explicit wind/brass stems")

        curation_path = (
            TRAINING_ROOT
            / "source_receipts/onair_music/v4-1cdaae8"
            / f"{selection_name}.json"
        )
        curation_path.parent.mkdir(parents=True, exist_ok=True)
        curation_path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "source_id": "onair_music",
                    "selection_name": selection_name,
                    "method": "explicit_archive_stem_labels",
                    "selected_file_count": len(family_assignments),
                    "selected_paths": sorted(family_assignments),
                    "excluded_policy": (
                        "exclude generic guitar, keys, chords, melodies, and "
                        "pluck labels because they do not prove a specialist "
                        "family"
                    ),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        output_dir = (
            TRAINING_ROOT
            / "source_items/onair_music/v4-1cdaae8"
            / selection_name
        )
        report = audit_training_tree(
            "onair_music",
            source_root,
            output_dir=output_dir,
            provenance_sha256=file_checksum(curation_path),
            selected_paths=set(family_assignments),
            family_assignments=family_assignments,
        )
        training_volume.commit()
        return report

    @app.function(
        image=image,
        gpu=os.getenv("SPECIALIST_TRAINING_GPU", "H100"),
        cpu=float(os.getenv("SPECIALIST_TRAINING_CPU", "8")),
        memory=int(os.getenv("SPECIALIST_TRAINING_MEMORY_MB", "49152")),
        timeout=int(os.getenv("SPECIALIST_TRAINING_TIMEOUT", "86400")),
        volumes={str(TRAINING_ROOT): training_volume},
        secrets=[modal.Secret.from_name("stemsplitter-wandb")],
    )
    def train_specialist(
        base_id: str,
        run_id: str,
        steps: int,
        epochs: int,
        resume_checkpoint: str = "",
        resume_mode: str = "state",
        dataset_id: str = "complete-source-pools",
        adaptation_mode: str = "full",
        validation_set_id: str = "",
        training_recipe: str = "legacy",
    ) -> dict[str, Any]:
        if base_id not in BASE_IDS:
            raise ValueError(f"unsupported base: {base_id}")
        if steps < 1 or epochs < 1:
            raise ValueError("steps and epochs must be positive")
        if not DATASET_ID_PATTERN.fullmatch(dataset_id):
            raise ValueError("invalid dataset_id")
        if adaptation_mode not in {"full", "head"}:
            raise ValueError("adaptation_mode must be full or head")
        if training_recipe not in {"legacy", "recovery_v1"}:
            raise ValueError("training_recipe must be legacy or recovery_v1")
        if resume_mode not in {"state", "weights"}:
            raise ValueError("resume_mode must be state or weights")
        if not resume_checkpoint and resume_mode != "state":
            raise ValueError(
                "resume_mode weights requires a resume_checkpoint"
            )
        if (
            validation_set_id
            and not DATASET_ID_PATTERN.fullmatch(validation_set_id)
        ):
            raise ValueError("invalid validation_set_id")

        import torch

        base_root = TRAINING_ROOT / "bases"
        index_root = TRAINING_ROOT / "indexes" / dataset_id
        validation_root = _validation_root(base_id, validation_set_id)
        run_root = TRAINING_ROOT / "runs" / run_id / base_id
        run_root.mkdir(parents=True, exist_ok=True)
        source_config = base_root / f"{base_id}_bsroformer_stage_25.yaml"
        base_checkpoint = base_root / f"{base_id}_bsroformer_base.ckpt"
        metadata_cache = index_root / f"{base_id}.metadata.pkl"
        start_checkpoint = (
            TRAINING_ROOT / resume_checkpoint
            if resume_checkpoint
            else base_checkpoint
        )
        for required in (
            source_config,
            start_checkpoint,
            index_root / f"{base_id}.csv",
            index_root / "index.json",
            metadata_cache,
            validation_root,
        ):
            if not required.exists():
                raise FileNotFoundError(str(required))
        indexed_audio_count = _assert_index_materialized(
            index_root / f"{base_id}.csv"
        )

        config = yaml.load(
            source_config.read_text(encoding="utf-8"),
            Loader=yaml.FullLoader,
        )
        config["training"]["num_steps"] = int(steps)
        config["training"]["num_epochs"] = int(epochs)
        config["training"]["patience"] = max(int(epochs), 2)
        # Sample corpora uniformly before sampling files so large one-shot
        # collections augment, rather than overwhelm, real performances.
        config["training"]["source_sampling_temperature"] = 0.0
        if training_recipe == "recovery_v1":
            config["training"].update(
                {
                    "augmentation": False,
                    "augmentation_mix": False,
                    "augmentation_loudness": False,
                    "aligned_mix_probability": 0.5,
                    "aligned_max_interferers": 3,
                    "target_background_snr_db": [0.0, 10.0],
                    "mixture_peak_limit": 0.99,
                }
            )
            config["augmentations"] = {"enable": False}
        runtime_config = run_root / "runtime.yaml"
        runtime_config.write_text(
            yaml.dump(config, Dumper=yaml.Dumper, sort_keys=False),
            encoding="utf-8",
        )
        run_metadata_cache = run_root / "metadata_3.pkl"
        if not run_metadata_cache.is_file():
            shutil.copy2(metadata_cache, run_metadata_cache)

        command = [
            sys.executable,
            "/root/msst/train.py",
            "--model_type",
            "bs_roformer",
            "--config_path",
            str(runtime_config),
            "--start_check_point",
            str(start_checkpoint),
            "--results_path",
            str(run_root),
            "--data_path",
            str(index_root / f"{base_id}.csv"),
            "--valid_path",
            str(validation_root),
            "--dataset_type",
            "3",
            "--num_workers",
            "4" if training_recipe == "recovery_v1" else "8",
            "--seed",
            "20260727",
            "--device_ids",
            "0",
            "--metrics",
            "sdr",
            "bleedless",
            "fullness",
            "--metric_for_scheduler",
            "sdr",
            "--pin_memory",
            "--persistent_workers",
            "--prefetch_factor",
            "2" if training_recipe == "recovery_v1" else "4",
            "--save_weights_every_epoch",
            "--pre_valid",
        ]
        if resume_checkpoint:
            if resume_mode == "state":
                command.extend(
                    [
                        "--load_optimizer",
                        "--load_scheduler",
                        "--load_epoch",
                        "--load_best_metric",
                        "--load_all_metrics",
                        "--load_all_losses",
                    ]
                )
            # With no load flags, MSST extracts model_state_dict from a full
            # checkpoint while creating fresh optimizer and epoch state.
        else:
            command.append("--load_only_compatible_weights")
        if adaptation_mode == "head":
            command.extend(
                ["--train_only_prefixes", "mask_estimators.0"]
            )

        started = time.perf_counter()
        environment = dict(os.environ)
        wandb_root = run_root / "wandb"
        wandb_root.mkdir(parents=True, exist_ok=True)
        environment["WANDB_DIR"] = str(wandb_root)
        environment["WANDB_MODE"] = (
            "online" if environment.get("WANDB_API_KEY") else "offline"
        )
        environment["WANDB_RUN_GROUP"] = run_id
        environment["WANDB_RUN_NAME"] = (
            f"{run_id}-{base_id}-epoch-{epochs}-steps-{steps}"
        )
        environment["WANDB_JOB_TYPE"] = base_id
        if not environment.get("WANDB_API_KEY"):
            command.append("--wandb_offline")
        completed = subprocess.run(
            command,
            cwd="/root/msst",
            env=environment,
            check=False,
        )
        elapsed = time.perf_counter() - started
        if completed.returncode != 0:
            raise RuntimeError(
                f"trainer failed with status {completed.returncode}"
            )
        checkpoint = run_root / "last_bs_roformer.ckpt"
        if not checkpoint.is_file():
            raise RuntimeError("trainer produced no resumable checkpoint")

        device = torch.cuda.get_device_properties(0)
        receipt = {
            "schema_version": "1.0",
            "base_id": base_id,
            "run_id": run_id,
            "dataset_id": dataset_id,
            "adaptation_mode": adaptation_mode,
            "training_recipe": training_recipe,
            "resume_mode": resume_mode if resume_checkpoint else "base_weights",
            "validation_set_id": validation_set_id or "sprint-stage-25",
            "indexed_audio_count": indexed_audio_count,
            "dataset_receipt_sha256": _sha256(
                index_root / "index.json"
            ),
            "steps_per_epoch": steps,
            "epochs": epochs,
            "elapsed_seconds": round(elapsed, 3),
            "seconds_per_step": round(elapsed / (steps * epochs), 6),
            "gpu_name": device.name,
            "gpu_memory_bytes": int(device.total_memory),
            "peak_gpu_memory_bytes": int(torch.cuda.max_memory_allocated()),
            "start_checkpoint": str(start_checkpoint.relative_to(TRAINING_ROOT)),
            "start_checkpoint_sha256": _sha256(start_checkpoint),
            "checkpoint": str(checkpoint.relative_to(TRAINING_ROOT)),
            "checkpoint_sha256": _sha256(checkpoint),
            "config_sha256": _sha256(runtime_config),
        }
        (run_root / "modal-receipt.json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        training_volume.commit()
        return receipt


    @app.function(
        image=image,
        gpu=os.getenv("SPECIALIST_TRAINING_GPU", "H100"),
        cpu=float(os.getenv("SPECIALIST_TRAINING_CPU", "8")),
        memory=int(os.getenv("SPECIALIST_TRAINING_MEMORY_MB", "49152")),
        timeout=int(os.getenv("SPECIALIST_TRAINING_TIMEOUT", "7200")),
        volumes={str(TRAINING_ROOT): training_volume},
        secrets=[modal.Secret.from_name("stemsplitter-wandb")],
    )
    def export_specialist(
        base_id: str,
        run_id: str,
        max_examples: int = 3,
        dataset_id: str = "complete-source-pools",
        validation_set_id: str = "",
        comparison_checkpoint: str = "",
        comparison_label: str = "",
        evaluation_id: str = "",
    ) -> dict[str, Any]:
        import torch

        if base_id not in BASE_IDS:
            raise ValueError(f"unsupported base: {base_id}")
        if max_examples < 1:
            raise ValueError("max_examples must be positive")
        if not DATASET_ID_PATTERN.fullmatch(dataset_id):
            raise ValueError("invalid dataset_id")
        for identifier_name, identifier in (
            ("validation_set_id", validation_set_id),
            ("comparison_label", comparison_label),
            ("evaluation_id", evaluation_id),
        ):
            if identifier and not DATASET_ID_PATTERN.fullmatch(identifier):
                raise ValueError(f"invalid {identifier_name}")
        comparison_path = Path(comparison_checkpoint)
        if comparison_checkpoint and (
            comparison_path.is_absolute() or ".." in comparison_path.parts
        ):
            raise ValueError("comparison checkpoint must be volume-relative")

        validation_root = _validation_root(base_id, validation_set_id)
        run_root = TRAINING_ROOT / "runs" / run_id / base_id
        resumable_checkpoint = run_root / "last_bs_roformer.ckpt"
        checkpoint = (
            TRAINING_ROOT / comparison_path
            if comparison_checkpoint
            else resumable_checkpoint
        )
        base_checkpoint = (
            TRAINING_ROOT / "bases" / f"{base_id}_bsroformer_base.ckpt"
        )
        runtime_config = run_root / "runtime.yaml"
        for required in (
            checkpoint,
            base_checkpoint,
            runtime_config,
            validation_root,
        ):
            if not required.exists():
                raise FileNotFoundError(str(required))

        mixtures = sorted(validation_root.glob("*/mixture.flac"))
        target_name = base_id
        mixtures = [
            path
            for path in mixtures
            if (path.parent / f"{target_name}.flac").is_file()
        ]
        selected = mixtures[:max_examples]
        if not selected:
            raise RuntimeError("no validation mixtures found")

        input_root = Path("/tmp") / f"{run_id}-{base_id}-inputs"
        shutil.rmtree(input_root, ignore_errors=True)
        input_root.mkdir(parents=True)
        for mixture in selected:
            shutil.copy2(mixture, input_root / f"{mixture.parent.name}.flac")

        export_root = (
            TRAINING_ROOT
            / "exports"
            / (evaluation_id or run_id)
            / base_id
        )
        shutil.rmtree(export_root, ignore_errors=True)
        export_root.mkdir(parents=True)
        started = time.perf_counter()

        comparison_variant = comparison_label or "trained_ema_1000"
        comparison_weight_source = "model_state_dict"
        comparison_eval_checkpoint = checkpoint
        if not comparison_checkpoint:
            # The trainer validates its EMA model but stores raw weights as
            # the primary state in the resumable checkpoint.
            resumable_payload = torch.load(
                checkpoint,
                map_location="cpu",
                weights_only=False,
            )
            ema_state = resumable_payload.get("ema_model_state_dict")
            if not ema_state:
                raise RuntimeError(
                    "resumable checkpoint has no EMA state to evaluate"
                )
            ema_model_state = {
                key.removeprefix("module."): value
                for key, value in ema_state.items()
                if key != "n_averaged"
            }
            comparison_eval_checkpoint = (
                Path("/tmp") / f"{run_id}-{base_id}-ema-eval.ckpt"
            )
            torch.save(
                {"model_state_dict": ema_model_state},
                comparison_eval_checkpoint,
            )
            comparison_weight_source = "ema_model_state_dict"
        variant_checkpoints = {
            "base": base_checkpoint,
            comparison_variant: comparison_eval_checkpoint,
        }
        for variant, variant_checkpoint in variant_checkpoints.items():
            command = [
                sys.executable,
                "/root/msst/inference.py",
                "--model_type",
                "bs_roformer",
                "--config_path",
                str(runtime_config),
                "--start_check_point",
                str(variant_checkpoint),
                "--input_folder",
                str(input_root),
                "--store_dir",
                str(export_root / variant),
                "--device_ids",
                "0",
                "--disable_detailed_pbar",
                "--flac_file",
                "--pcm_type",
                "PCM_24",
            ]
            completed = subprocess.run(command, cwd="/root/msst", check=False)
            if completed.returncode != 0:
                raise RuntimeError(
                    f"{variant} inference failed with status "
                    f"{completed.returncode}"
                )

        reference_root = export_root / "references"
        for mixture in selected:
            example_root = reference_root / mixture.parent.name
            example_root.mkdir(parents=True, exist_ok=True)
            shutil.copy2(mixture, example_root / "reference_mixture.flac")
            reference = mixture.parent / f"{target_name}.flac"
            shutil.copy2(
                reference,
                example_root / f"reference_{target_name}.flac",
            )

        import statistics

        import soundfile as sf

        sys.path.insert(0, "/root/msst")
        from utils.metrics import get_metrics

        def load_audio(path: Path) -> tuple[Any, int]:
            audio, sample_rate = sf.read(
                path,
                dtype="float32",
                always_2d=True,
            )
            return audio.T, int(sample_rate)

        scores: dict[str, Any] = {
            "per_example": {},
            "aggregate": {},
            "delta_comparison_minus_base": {},
            "delta_distribution": {},
        }
        metric_names = ["sdr", "bleedless", "fullness"]
        for mixture in selected:
            example_id = mixture.parent.name
            reference, reference_rate = load_audio(
                mixture.parent / f"{target_name}.flac"
            )
            mix, mix_rate = load_audio(mixture)
            if reference_rate != mix_rate:
                raise RuntimeError(
                    f"sample-rate mismatch for {example_id}"
                )
            example_scores: dict[str, Any] = {}
            for variant in variant_checkpoints:
                prediction_root = export_root / variant / example_id
                predictions = sorted(
                    prediction_root.glob(f"{target_name}.*")
                )
                if len(predictions) != 1:
                    raise RuntimeError(
                        f"expected one {variant} prediction for {example_id}"
                    )
                estimate, estimate_rate = load_audio(predictions[0])
                if estimate_rate != reference_rate:
                    raise RuntimeError(
                        f"prediction sample-rate mismatch for {example_id}"
                    )
                example_scores[variant] = get_metrics(
                    metric_names,
                    reference,
                    estimate,
                    mix,
                    device="cuda",
                )
            scores["per_example"][example_id] = example_scores

        for variant in variant_checkpoints:
            scores["aggregate"][variant] = {
                metric: statistics.fmean(
                    scores["per_example"][example_id][variant][metric]
                    for example_id in scores["per_example"]
                )
                for metric in metric_names
            }
        scores["delta_comparison_minus_base"] = {
            metric: (
                scores["aggregate"][comparison_variant][metric]
                - scores["aggregate"]["base"][metric]
            )
            for metric in metric_names
        }
        for metric in metric_names:
            deltas = [
                variants[comparison_variant][metric]
                - variants["base"][metric]
                for variants in scores["per_example"].values()
            ]
            scores["delta_distribution"][metric] = {
                "median": statistics.median(deltas),
                "improved_examples": sum(delta > 0 for delta in deltas),
                "example_count": len(deltas),
            }
        elapsed = time.perf_counter() - started

        wandb_root = export_root / "wandb"
        wandb_root.mkdir(parents=True, exist_ok=True)
        os.environ["WANDB_DIR"] = str(wandb_root)
        import wandb

        wandb_run = wandb.init(
            entity=os.getenv("WANDB_ENTITY"),
            project=os.getenv("WANDB_PROJECT"),
            name=(
                f"{evaluation_id or run_id}-{base_id}-"
                f"{comparison_variant}-comparison"
            ),
            group=run_id,
            job_type=f"{base_id}-evaluation",
            config={
                "base_id": base_id,
                "run_id": run_id,
                "dataset_id": dataset_id,
                "validation_set_id": validation_set_id or "sprint-stage-25",
                "comparison_variant": comparison_variant,
                "example_count": len(selected),
                "base_checkpoint_sha256": _sha256(base_checkpoint),
                "comparison_checkpoint_sha256": _sha256(checkpoint),
                "comparison_weight_source": comparison_weight_source,
            },
        )
        wandb_run.log(
            {
                f"base/{metric}": scores["aggregate"]["base"][metric]
                for metric in metric_names
            }
            | {
                f"comparison/{metric}": (
                    scores["aggregate"][comparison_variant][metric]
                )
                for metric in metric_names
            }
            | {
                f"delta_comparison_minus_base/{metric}": (
                    scores["delta_comparison_minus_base"][metric]
                )
                for metric in metric_names
            }
            | {
                f"delta_median/{metric}": (
                    scores["delta_distribution"][metric]["median"]
                )
                for metric in metric_names
            }
            | {
                f"improvement_rate/{metric}": (
                    scores["delta_distribution"][metric][
                        "improved_examples"
                    ]
                    / scores["delta_distribution"][metric]["example_count"]
                )
                for metric in metric_names
            }
        )
        wandb_url = wandb_run.url
        wandb_run.finish()

        audio_files = sorted(
            str(path.relative_to(TRAINING_ROOT))
            for path in export_root.rglob("*")
            if path.suffix.lower() in {".flac", ".wav"}
        )
        receipt = {
            "schema_version": "1.0",
            "base_id": base_id,
            "run_id": run_id,
            "dataset_id": dataset_id,
            "validation_set_id": validation_set_id or "sprint-stage-25",
            "evaluation_id": evaluation_id or run_id,
            "elapsed_seconds": round(elapsed, 3),
            "base_checkpoint_sha256": _sha256(base_checkpoint),
            "comparison_variant": comparison_variant,
            "comparison_checkpoint_sha256": _sha256(checkpoint),
            "comparison_weight_source": comparison_weight_source,
            "example_count": len(selected),
            "scores": scores,
            "wandb_url": wandb_url,
            "audio_files": audio_files,
        }
        (export_root / "export-receipt.json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        training_volume.commit()
        return receipt


    def _verify_training_dataset(
        dataset_id: str = "complete-source-pools",
    ) -> dict[str, Any]:
        if not DATASET_ID_PATTERN.fullmatch(dataset_id):
            raise ValueError("invalid dataset_id")

        index_root = TRAINING_ROOT / "indexes" / dataset_id
        index_manifest = index_root / "index.json"
        report: dict[str, Any] = {
            "dataset_id": dataset_id,
            "ready": True,
            "indexes": {},
        }
        fingerprint = hashlib.sha256()
        manifest_payload: dict[str, Any] = {}

        if not index_manifest.is_file():
            report["ready"] = False
            report["index_manifest_missing"] = str(index_manifest)
        else:
            manifest_payload = json.loads(
                index_manifest.read_text(encoding="utf-8")
            )
            manifest_sha256 = _sha256(index_manifest)
            report["index_manifest_sha256"] = manifest_sha256
            fingerprint.update(manifest_sha256.encode())

        for base_id in sorted(DATASET_FAMILIES):
            index_path = index_root / f"{base_id}.csv"
            index_report: dict[str, Any] = {
                "path": str(index_path),
                "rows": 0,
                "missing_count": 0,
                "missing_examples": [],
            }
            if not index_path.is_file():
                index_report["missing_count"] = 1
                index_report["missing_examples"] = [str(index_path)]
                report["ready"] = False
                report["indexes"][base_id] = index_report
                continue

            index_sha256 = _sha256(index_path)
            index_report["sha256"] = index_sha256
            fingerprint.update(f"{base_id}:{index_sha256}".encode())
            semantic_digest = hashlib.sha256()
            first_semantic_row = True
            counts: dict[str, int] = {}
            sources: set[str] = set()
            with index_path.open(encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle):
                    index_report["rows"] += 1
                    label = str(row["instrum"])
                    counts[label] = counts.get(label, 0) + 1
                    sources.add(str(row["source_id"]))
                    if not first_semantic_row:
                        semantic_digest.update(b"\n")
                    semantic_digest.update(
                        (
                            f"{row['instrum']},{row['path']},{row['sha256']}"
                        ).encode()
                    )
                    first_semantic_row = False
                    path = Path(str(row["path"]))
                    if not path.is_file():
                        index_report["missing_count"] += 1
                        if len(index_report["missing_examples"]) < 20:
                            index_report["missing_examples"].append(str(path))

            family_manifest = (
                manifest_payload.get("families", {}).get(base_id, {})
            )
            semantic_sha256 = semantic_digest.hexdigest()
            index_report["semantic_sha256"] = semantic_sha256
            index_report["manifest_semantic_sha256"] = family_manifest.get(
                "sha256"
            )
            index_report["manifest_digest_matches"] = (
                semantic_sha256 == family_manifest.get("sha256")
            )
            index_report["counts"] = counts
            index_report["sources"] = sorted(sources)
            index_report["stored_pending_materialization_count"] = (
                family_manifest.get("pending_materialization_count")
            )
            index_report["manifest_row_count_matches"] = (
                index_report["rows"] == family_manifest.get("row_count")
            )
            index_report["manifest_counts_match"] = (
                counts == family_manifest.get("counts")
            )
            if index_report["missing_count"]:
                report["ready"] = False
            if not all(
                (
                    index_report["manifest_digest_matches"],
                    index_report["manifest_row_count_matches"],
                    index_report["manifest_counts_match"],
                )
            ):
                report["ready"] = False
            report["indexes"][base_id] = index_report

        report["dataset_fingerprint"] = fingerprint.hexdigest()
        return report


    @app.function(
        image=image,
        cpu=1,
        memory=2048,
        timeout=1800,
        volumes={str(TRAINING_ROOT): training_volume},
    )
    def verify_training_dataset(
        dataset_id: str = "complete-source-pools",
    ) -> dict[str, Any]:
        return _verify_training_dataset(dataset_id)


    @app.function(
        image=image,
        cpu=0.25,
        memory=256,
        timeout=60,
        secrets=[modal.Secret.from_name("stemsplitter-wandb")],
    )
    def verify_training_monitoring() -> dict[str, Any]:
        import wandb

        run = wandb.init(
            entity=os.getenv("WANDB_ENTITY"),
            project=os.getenv("WANDB_PROJECT"),
            name="modal-monitoring-smoke",
            job_type="monitoring",
            config={"source": "specialist_training_modal"},
        )
        run.log({"monitoring_smoke": 1})
        run_url = run.url
        run.finish()
        return {
            "wandb_configured": bool(os.getenv("WANDB_API_KEY", "").strip()),
            "wandb_entity": os.getenv("WANDB_ENTITY"),
            "wandb_project": os.getenv("WANDB_PROJECT"),
            "wandb_run_url": run_url,
        }


    @app.function(
        image=image,
        cpu=16,
        memory=8192,
        timeout=7200,
        volumes={str(TRAINING_ROOT): training_volume},
    )
    def prepare_training_metadata(
        dataset_id: str = "complete-source-pools",
    ) -> dict[str, Any]:
        if not DATASET_ID_PATTERN.fullmatch(dataset_id):
            raise ValueError("invalid dataset_id")

        index_root = TRAINING_ROOT / "indexes" / dataset_id
        rows_by_base: dict[str, list[dict[str, str]]] = {}
        required_sha256: set[str] = set()
        for base_id in sorted(DATASET_FAMILIES):
            index_path = index_root / f"{base_id}.csv"
            with index_path.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            rows_by_base[base_id] = rows
            required_sha256.update(str(row["sha256"]) for row in rows)

        frames_by_sha256: dict[str, int] = {}
        item_root = Path("/root/project/datasets/manifests/items")
        for manifest_path in item_root.rglob("*.jsonl"):
            with manifest_path.open(encoding="utf-8") as handle:
                for line in handle:
                    item = json.loads(line)
                    audio = item.get("audio") or {}
                    sha256 = str(audio.get("sha256") or "")
                    frames = audio.get("frames")
                    if sha256 not in required_sha256 or frames is None:
                        continue
                    frame_count = int(frames)
                    previous = frames_by_sha256.get(sha256)
                    if previous is not None and previous != frame_count:
                        raise RuntimeError(
                            f"conflicting frame counts for {sha256}"
                        )
                    frames_by_sha256[sha256] = frame_count

        missing_sha256 = required_sha256 - frames_by_sha256.keys()
        if missing_sha256:
            examples = ", ".join(sorted(missing_sha256)[:20])
            raise RuntimeError(
                "item manifests lack frame metadata for "
                f"{len(missing_sha256)} indexed files: {examples}"
            )

        caches: dict[str, dict[str, Any]] = {}
        for base_id, rows in rows_by_base.items():
            metadata: dict[str, list[tuple[str, int]]] = {}
            for row in rows:
                label = str(row["instrum"])
                path = str(row["path"])
                frames = frames_by_sha256[str(row["sha256"])]
                metadata.setdefault(label, []).append((path, frames))

            cache_path = index_root / f"{base_id}.metadata.pkl"
            temporary_path = cache_path.with_suffix(".pkl.tmp")
            with temporary_path.open("wb") as handle:
                pickle.dump(metadata, handle, protocol=pickle.HIGHEST_PROTOCOL)
            temporary_path.replace(cache_path)
            caches[base_id] = {
                "path": str(cache_path.relative_to(TRAINING_ROOT)),
                "sha256": _sha256(cache_path),
                "counts": {
                    label: len(entries)
                    for label, entries in sorted(metadata.items())
                },
            }

        receipt = {
            "schema_version": "1.0",
            "dataset_id": dataset_id,
            "unique_audio_files": len(required_sha256),
            "frame_metadata_source": "curated_item_manifests",
            "caches": caches,
        }
        receipt_path = index_root / "metadata-receipt.json"
        receipt_path.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        training_volume.commit()
        return receipt


    @app.function(
        image=image,
        cpu=2,
        memory=4096,
        timeout=600,
        volumes={str(TRAINING_ROOT): training_volume},
    )
    def export_dataset_audit(
        dataset_id: str = "complete-source-pools",
        audit_id: str = "modal-corpus-fast-audit-v1",
    ) -> dict[str, Any]:
        if not DATASET_ID_PATTERN.fullmatch(dataset_id):
            raise ValueError("invalid dataset_id")
        if not DATASET_ID_PATTERN.fullmatch(audit_id):
            raise ValueError("invalid audit_id")

        readiness = _verify_training_dataset(dataset_id)
        if not readiness["ready"]:
            raise RuntimeError("training dataset is not ready")

        export_root = TRAINING_ROOT / "exports" / audit_id
        manifest_path = export_root / "manifest.json"
        if manifest_path.is_file():
            return json.loads(manifest_path.read_text(encoding="utf-8"))

        index_root = TRAINING_ROOT / "indexes" / dataset_id
        clips: list[dict[str, Any]] = []
        for base_id in sorted(DATASET_FAMILIES):
            with (index_root / f"{base_id}.csv").open(
                encoding="utf-8",
                newline="",
            ) as handle:
                rows = list(csv.DictReader(handle))

            selected: list[dict[str, str]] = []
            selected_sources: set[str] = set()
            for row in rows:
                source_id = str(row["source_id"])
                if (
                    row["instrum"] == base_id
                    and source_id not in selected_sources
                ):
                    selected.append(row)
                    selected_sources.add(source_id)
                    if len(selected) == 3:
                        break
            negative = next(
                row for row in rows if row["instrum"] == "other"
            )
            selected.append(negative)

            family_root = export_root / base_id
            family_root.mkdir(parents=True, exist_ok=True)
            for position, row in enumerate(selected, start=1):
                label = str(row["instrum"])
                source_id = str(row["source_id"])
                output = family_root / (
                    f"{position:02d}-{label}-{source_id}-"
                    f"{str(row['sha256'])[:12]}.flac"
                )
                completed = subprocess.run(
                    [
                        "ffmpeg",
                        "-nostdin",
                        "-v",
                        "error",
                        "-i",
                        str(row["path"]),
                        "-af",
                        (
                            "silenceremove=start_periods=1:"
                            "start_duration=0.1:start_threshold=-45dB"
                        ),
                        "-t",
                        "12",
                        "-ar",
                        "44100",
                        "-ac",
                        "2",
                        "-compression_level",
                        "5",
                        str(output),
                    ],
                    check=False,
                )
                if completed.returncode != 0 or not output.is_file():
                    raise RuntimeError(
                        f"failed to render audit clip from {row['path']}"
                    )
                clips.append(
                    {
                        "family": base_id,
                        "expected_label": label,
                        "source_id": source_id,
                        "source_path": str(row["path"]),
                        "source_sha256": str(row["sha256"]),
                        "clip": str(output.relative_to(export_root)),
                    }
                )

        manifest = {
            "audit_id": audit_id,
            "dataset_id": dataset_id,
            "dataset_fingerprint": readiness["dataset_fingerprint"],
            "clip_count": len(clips),
            "clips": clips,
        }
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        training_volume.commit()
        return manifest


    @app.function(
        image=image,
        cpu=2,
        memory=4096,
        timeout=1800,
        volumes={str(TRAINING_ROOT): training_volume},
        secrets=[
            modal.Secret.from_name(
                os.getenv(
                    "OBJECT_STORAGE_MODAL_SECRET",
                    "stemsplitter-b2",
                )
            )
        ],
    )
    def publish_training_dataset_snapshot(
        dataset_id: str = "complete-source-pools",
    ) -> dict[str, Any]:
        sys.path.insert(0, "/root/project")
        from splitter.object_storage import (
            ObjectStorageError,
            object_store_from_config,
        )

        report = _verify_training_dataset(dataset_id)
        if not report["ready"]:
            raise RuntimeError("training dataset is not ready")

        store = object_store_from_config()
        if store is None:
            raise RuntimeError("object storage is not configured")
        fingerprint = str(report["dataset_fingerprint"])
        key = (
            f"{store.prefix}/training-datasets/{dataset_id}/"
            f"{fingerprint}/metadata.tar.gz"
        )
        reference = {
            "provider": "s3",
            "bucket": store.bucket,
            "key": key,
        }
        try:
            existing = store.stat(reference)
        except ObjectStorageError:
            existing = None
        if existing is not None:
            return {
                "dataset_id": dataset_id,
                "dataset_fingerprint": fingerprint,
                "object": existing.as_dict(),
                "reused": True,
            }

        snapshot_root = Path("/tmp") / f"training-snapshot-{fingerprint}"
        snapshot_root.mkdir(parents=True, exist_ok=True)
        report["audio_mirrored"] = False
        report["audio_materialization"] = "verified-source-receipts"
        report_path = snapshot_root / "snapshot.json"
        report_path.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        archive_path = snapshot_root.with_suffix(".tar.gz")
        index_root = TRAINING_ROOT / "indexes" / dataset_id
        with tarfile.open(archive_path, "w:gz") as archive:
            archive.add(
                report_path,
                arcname="snapshot.json",
            )
            archive.add(
                index_root,
                arcname=f"indexes/{dataset_id}",
            )
            archive.add(
                TRAINING_ROOT / "source_receipts",
                arcname="source_receipts",
            )
            for source_root, archive_name in (
                (
                    TRAINING_ROOT / "source_audio/datasets/staging",
                    "completion_markers/staging",
                ),
                (
                    TRAINING_ROOT / "source_audio/datasets/extracted",
                    "completion_markers/extracted",
                ),
            ):
                for marker in sorted(source_root.rglob(".modal-*.json")):
                    archive.add(
                        marker,
                        arcname=str(
                            Path(archive_name)
                            / marker.relative_to(source_root)
                        ),
                    )

        uploaded = store.upload(
            archive_path,
            key,
            "application/gzip",
        )
        verified = store.stat(uploaded.as_dict())
        shutil.rmtree(snapshot_root, ignore_errors=True)
        archive_path.unlink(missing_ok=True)
        return {
            "dataset_id": dataset_id,
            "dataset_fingerprint": fingerprint,
            "object": verified.as_dict(),
            "reused": False,
        }

    @app.function(
        image=image,
        cpu=16,
        memory=32768,
        timeout=21600,
        volumes={str(TRAINING_ROOT): training_volume},
    )
    def build_specialist_validation(
        base_id: str,
        set_id: str,
        count: int = 30,
    ) -> dict[str, Any]:
        if base_id not in BASE_IDS:
            raise ValueError(f"unsupported base: {base_id}")
        if not DATASET_ID_PATTERN.fullmatch(set_id):
            raise ValueError("invalid validation set ID")
        if count < 1:
            raise ValueError("validation count must be positive")

        environment = dict(os.environ)
        environment["STEM_SPLITTER_TRAINING_ROOT"] = str(TRAINING_ROOT)
        commands = (
            [
                sys.executable,
                "/root/project/scripts/build_training_manifest.py",
                "--profile",
                "research_all",
                "--family",
                base_id,
                "--validation-only",
            ],
            [
                sys.executable,
                "/root/project/scripts/build_specialist_validation_set.py",
                "--profile",
                "research_all",
                "--family",
                base_id,
                "--set-id",
                set_id,
                "--count",
                str(count),
                "--render-root",
                str(TRAINING_ROOT / "validation_renders"),
                "--output-root",
                str(TRAINING_ROOT / "validation_sets"),
            ],
        )
        for command in commands:
            completed = subprocess.run(
                command,
                cwd="/root/project",
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.returncode != 0:
                reason = completed.stderr.strip() or completed.stdout.strip()
                raise RuntimeError(
                    f"validation preparation failed: {reason}"
                )

        receipt_path = (
            TRAINING_ROOT / "validation_sets" / set_id / "validation-set.json"
        )
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        training_volume.commit()
        return {
            "set_id": set_id,
            "base_id": base_id,
            "count": receipt["families"][base_id]["count"],
            "composition_count": receipt["families"][base_id][
                "composition_count"
            ],
            "receipt": str(receipt_path),
        }


    @app.function(
        image=image,
        cpu=2,
        memory=4096,
        timeout=1800,
        volumes={str(TRAINING_ROOT): training_volume},
    )
    def install_validation_set(
        archive_name: str,
        set_id: str,
        expected_sha256: str,
    ) -> dict[str, Any]:
        if not DATASET_ID_PATTERN.fullmatch(set_id):
            raise ValueError("invalid validation set ID")
        if not re.fullmatch(r"[a-f0-9]{64}", expected_sha256):
            raise ValueError("invalid archive SHA-256")
        archive_path = TRAINING_ROOT / "uploads" / archive_name
        if not archive_path.is_file():
            raise FileNotFoundError(str(archive_path))
        if _sha256(archive_path) != expected_sha256:
            raise RuntimeError("validation archive SHA-256 mismatch")

        validation_root = TRAINING_ROOT / "validation_sets"
        target_root = validation_root / set_id
        receipt_path = target_root / "validation-set.json"
        if receipt_path.is_file():
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            return {
                "set_id": set_id,
                "reused": True,
                "flac_count": sum(1 for _ in target_root.rglob("*.flac")),
                "receipt": receipt,
            }

        temporary_root = validation_root / f".{set_id}.installing"
        shutil.rmtree(temporary_root, ignore_errors=True)
        temporary_root.mkdir(parents=True)
        try:
            with tarfile.open(archive_path, "r:gz") as archive:
                for member in archive.getmembers():
                    member_path = Path(member.name)
                    if (
                        member_path.is_absolute()
                        or ".." in member_path.parts
                        or not member_path.parts
                        or member_path.parts[0] != set_id
                        or member.issym()
                        or member.islnk()
                        or member.isdev()
                    ):
                        raise RuntimeError(
                            f"unsafe validation archive member: {member.name}"
                        )
                archive.extractall(temporary_root, filter="data")

            extracted_root = temporary_root / set_id
            extracted_receipt = extracted_root / "validation-set.json"
            if not extracted_receipt.is_file():
                raise RuntimeError("validation receipt is missing")
            receipt = json.loads(
                extracted_receipt.read_text(encoding="utf-8")
            )
            if receipt.get("set_id") != set_id:
                raise RuntimeError("validation receipt set ID mismatch")
            expected_flac_count = (
                int(receipt["count_per_family"])
                * len(receipt["families"])
                * 2
            )
            flac_count = sum(1 for _ in extracted_root.rglob("*.flac"))
            if flac_count != expected_flac_count:
                raise RuntimeError(
                    f"validation FLAC count mismatch: "
                    f"{flac_count}/{expected_flac_count}"
                )
            extracted_root.replace(target_root)
        finally:
            shutil.rmtree(temporary_root, ignore_errors=True)

        archive_path.unlink()
        training_volume.commit()
        return {
            "set_id": set_id,
            "reused": False,
            "flac_count": flac_count,
            "receipt": receipt,
        }


    @app.local_entrypoint()
    def main(
        base_id: str,
        run_id: str = "sprint-v1",
        steps: int = 100,
        epochs: int = 1,
        resume_checkpoint: str = "",
        resume_mode: str = "state",
        action: str = "train",
        max_examples: int = 3,
        dataset_id: str = "complete-source-pools",
        adaptation_mode: str = "full",
        training_recipe: str = "legacy",
        validation_archive: str = "",
        validation_set_id: str = "",
        validation_archive_sha256: str = "",
        comparison_checkpoint: str = "",
        comparison_label: str = "",
        evaluation_id: str = "",
        source_id: str = "",
        provider_prefix: str = "",
        provider_path: str = "",
        source_subpath: str = "",
        release_name: str = "",
        suffix: str = ".wav",
    ) -> None:
        if action == "train":
            result = train_specialist.remote(
                base_id,
                run_id,
                steps,
                epochs,
                resume_checkpoint,
                resume_mode,
                dataset_id,
                adaptation_mode,
                validation_set_id,
                training_recipe,
            )
        elif action == "export":
            result = export_specialist.remote(
                base_id,
                run_id,
                max_examples,
                dataset_id,
                validation_set_id,
                comparison_checkpoint,
                comparison_label,
                evaluation_id,
            )
        elif action == "prepare":
            result = prepare_source_archives.remote()
        elif action == "audit-rawstems":
            result = audit_rawstems_selection.remote()
        elif action == "acquire-prefix":
            result = acquire_huggingface_prefix.remote(
                source_id,
                provider_prefix,
                suffix,
            )
        elif action == "acquire-file":
            result = acquire_registered_file.remote(
                source_id,
                provider_path,
            )
        elif action == "audit-tree":
            result = audit_registered_tree.remote(
                source_id,
                source_subpath,
                release_name,
            )
        elif action == "extract-file":
            result = extract_registered_archive.remote(
                source_id,
                provider_path,
                release_name,
            )
        elif action == "curate-fsl10k":
            result = curate_fsl10k.remote()
        elif action == "curate-nsynth":
            result = curate_nsynth.remote()
        elif action == "prune-nsynth":
            result = prune_nsynth_unselected.remote()
        elif action == "curate-idmt-guitar":
            result = curate_idmt_smt_guitar.remote()
        elif action == "curate-onair":
            result = curate_onair_music.remote()
        elif action == "verify":
            result = verify_training_dataset.remote(dataset_id)
        elif action == "monitoring":
            result = verify_training_monitoring.remote()
        elif action == "metadata":
            result = prepare_training_metadata.remote(dataset_id)
        elif action == "snapshot":
            result = publish_training_dataset_snapshot.remote(dataset_id)
        elif action == "build-validation":
            result = build_specialist_validation.remote(
                base_id,
                validation_set_id,
                max_examples,
            )
        elif action == "audit":
            result = export_dataset_audit.remote(dataset_id)
        elif action == "install-validation":
            result = install_validation_set.remote(
                validation_archive,
                validation_set_id,
                validation_archive_sha256,
            )
        else:
            raise ValueError(
                "action must be 'train', 'export', 'prepare', 'verify', "
                "'monitoring', 'metadata', 'snapshot', 'audit', "
                "'audit-rawstems', 'acquire-prefix', 'acquire-file', "
                "'audit-tree', 'extract-file', 'curate-fsl10k', "
                "'curate-nsynth', 'curate-idmt-guitar', "
                "'build-validation', or "
                "'install-validation'"
            )
        print(json.dumps(result, sort_keys=True))
