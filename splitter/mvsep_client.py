"""MVSEP API Client for specialist model separation.

MVSEP (Music & Voice Separation) hosts 100+ community-trained models
for professional-grade stem separation. This client provides a simple
interface to chain specialist models for 16-stem separation.

See: https://mvsep.com/en
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from .util import ensure_dir


class MVSEPClient:
    """Client for MVSEP.com API.
    
    Usage:
        client = MVSEPClient()
        stems = client.separate(
            input_path=Path("track.wav"),
            model="BS-Roformer-V2",
            output_dir=Path("output/"),
        )
    """
    
    # MVSEP API endpoints
    BASE_URL = "https://mvsep.com/api/separate"
    STATUS_URL = "https://mvsep.com/api/status"
    
    # Available specialist models
    MODELS = {
        # Vocal models
        "BS-Roformer-V2": "Lead/Backing vocal separation",
        "BS-Roformer-ViperX-1296": "6-stem: vocals, bass, drums, guitar, piano, other",
        "UVR-BVE-Net": "Backing vocal extraction",
        "UVR-De-Reverb-Echo": "Vocal reverb/delay isolation",
        "Kim_Vocal_2": "High-quality vocal separation",
        
        # Drum models
        "DrumSep": "Individual drums: kick, snare, hats, cymbals, toms",
        "MVSep-Drums": "5-stem drum separation",
        
        # Instrument models
        "MVSep-Piano": "Piano isolation",
        "MVSep-Lead-Guitar": "Electric guitar isolation",
        "MVSep-Acoustic-Guitar": "Acoustic guitar isolation",
        "MVSep-Keys": "Keys/synth isolation",
        "MVSep-Plucked-Strings": "Strings, violin, cello",
        "MVSep-Brass": "Trumpet, saxophone, brass",
        "MVSep-Woodwind": "Flute, clarinet, woodwinds",
        
        # Utility models
        "Denoise-MDX23C": "Noise/crowd removal",
        "SCNet_Vanilla": "Fast instrumental separation",
    }
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout: int = 300,
        max_retries: int = 3,
        retry_delay: int = 5,
    ):
        """Initialize MVSEP client.
        
        Args:
            api_key: Optional API key for Pro tier
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts on failure
            retry_delay: Delay between retries in seconds
        """
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.session = requests.Session()
        
        if api_key:
            self.session.headers["Authorization"] = f"Bearer {api_key}"
    
    def separate(
        self,
        input_path: Path,
        model: str,
        output_dir: Path,
        output_format: str = "wav",
    ) -> Dict[str, Path]:
        """Separate audio using MVSEP specialist model.
        
        Args:
            input_path: Path to input audio file
            model: MVSEP model name (e.g., "BS-Roformer-V2", "DrumSep")
            output_dir: Directory to save output stems
            output_format: Output format (mp3, wav, flac)
        
        Returns:
            Dict mapping stem names to output file paths
        
        Raises:
            ValueError: If model is not available
            requests.RequestException: If API call fails
        """
        if model not in self.MODELS:
            raise ValueError(
                f"Unknown model: {model}. "
                f"Available models: {list(self.MODELS.keys())}"
            )
        
        ensure_dir(output_dir)
        
        # Upload and process
        for attempt in range(self.max_retries):
            try:
                return self._separate_with_retry(
                    input_path=input_path,
                    model=model,
                    output_dir=output_dir,
                    output_format=output_format,
                )
            except requests.RequestException as e:
                if attempt == self.max_retries - 1:
                    raise
                time.sleep(self.retry_delay * (attempt + 1))
        
        raise RuntimeError(f"Failed after {self.max_retries} attempts")
    
    def _separate_with_retry(
        self,
        input_path: Path,
        model: str,
        output_dir: Path,
        output_format: str,
    ) -> Dict[str, Path]:
        """Execute separation with status polling."""
        
        # Step 1: Upload file and start processing
        with open(input_path, "rb") as f:
            upload_response = self._upload_file(f, model, output_format)
        
        job_id = upload_response.get("job_id")
        if not job_id:
            raise RuntimeError("No job_id in upload response")
        
        # Step 2: Poll for completion
        result = self._poll_job_status(job_id)
        
        # Step 3: Download stems
        stems = {}
        for stem_name, stem_url in result.get("stems", {}).items():
            stem_path = self._download_stem(stem_url, output_dir, stem_name)
            stems[stem_name] = stem_path
        
        return stems
    
    def _upload_file(
        self,
        file_obj,
        model: str,
        output_format: str,
    ) -> Dict[str, Any]:
        """Upload file and start processing."""
        response = self.session.post(
            self.BASE_URL,
            files={"audio": file_obj},
            data={
                "model": model,
                "format": output_format,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()
    
    def _poll_job_status(self, job_id: str) -> Dict[str, Any]:
        """Poll job status until complete."""
        max_polls = 60  # Max 5 minutes (5s * 60)
        poll_interval = 5  # seconds
        
        for i in range(max_polls):
            response = self.session.get(
                f"{self.STATUS_URL}/{job_id}",
                timeout=30,
            )
            response.raise_for_status()
            status = response.json()
            
            if status.get("status") == "completed":
                return status
            elif status.get("status") == "failed":
                raise RuntimeError(f"Job failed: {status.get('error', 'Unknown error')}")
            
            time.sleep(poll_interval)
        
        raise RuntimeError(f"Job timed out after {max_polls * poll_interval}s")
    
    def _download_stem(
        self,
        stem_url: str,
        output_dir: Path,
        stem_name: str,
    ) -> Path:
        """Download individual stem file."""
        response = self.session.get(stem_url, timeout=60)
        response.raise_for_status()
        
        # Determine file extension from content type or URL
        ext = ".wav"  # Default
        if "flac" in stem_url.lower():
            ext = ".flac"
        elif "mp3" in stem_url.lower():
            ext = ".mp3"
        
        stem_path = output_dir / f"{stem_name}{ext}"
        stem_path.write_bytes(response.content)
        
        return stem_path
    
    def get_available_models(self) -> Dict[str, str]:
        """Get list of available models."""
        return self.MODELS.copy()
    
    def check_status(self) -> Dict[str, Any]:
        """Check API service status."""
        response = self.session.get(self.STATUS_URL, timeout=30)
        response.raise_for_status()
        return response.json()


class MVSEPModelChain:
    """Helper for chaining multiple MVSEP models.
    
    Usage:
        chain = MVSEPModelChain()
        stems = chain.run_16_stem("track.wav", output_dir)
    """
    
    def __init__(self, client: Optional[MVSEPClient] = None):
        self.client = client or MVSEPClient()
    
    def run_vocal_branch(
        self,
        vocals_path: Path,
        output_dir: Path,
    ) -> Dict[str, Path]:
        """Extract vocal sub-stems (lead, backing, reverb)."""
        vocal_dir = ensure_dir(output_dir / "vocals")
        stems = {}
        
        # Lead + Backing (BS-Roformer-V2)
        try:
            vocal_stems = self.client.separate(
                vocals_path,
                model="BS-Roformer-V2",
                output_dir=vocal_dir,
            )
            stems.update(vocal_stems)
        except Exception as e:
            print(f"BS-Roformer failed: {e}")
        
        # Vocal Reverb (UVR-De-Reverb-Echo)
        try:
            reverb_stems = self.client.separate(
                vocals_path,
                model="UVR-De-Reverb-Echo",
                output_dir=vocal_dir,
            )
            stems.update(reverb_stems)
        except Exception as e:
            print(f"De-Reverb failed: {e}")
        
        return stems
    
    def run_drum_branch(
        self,
        drums_path: Path,
        output_dir: Path,
    ) -> Dict[str, Path]:
        """Extract drum sub-stems (kick, snare, hats, cymbals, toms)."""
        drum_dir = ensure_dir(output_dir / "drums")
        
        return self.client.separate(
            drums_path,
            model="DrumSep",
            output_dir=drum_dir,
        )
    
    def run_instrument_branch(
        self,
        other_path: Path,
        output_dir: Path,
    ) -> Dict[str, Path]:
        """Extract instrument sub-stems (piano, guitar, keys, strings)."""
        instrument_dir = ensure_dir(output_dir / "instruments")
        stems = {}
        
        # Piano
        try:
            piano_stems = self.client.separate(
                other_path,
                model="MVSep-Piano",
                output_dir=instrument_dir,
            )
            stems.update(piano_stems)
        except Exception as e:
            print(f"MVSep-Piano failed: {e}")
        
        # Guitar
        try:
            guitar_stems = self.client.separate(
                other_path,
                model="MVSep-Lead-Guitar",
                output_dir=instrument_dir,
            )
            stems.update(guitar_stems)
        except Exception as e:
            print(f"MVSep-Guitar failed: {e}")
        
        # Keys
        try:
            keys_stems = self.client.separate(
                other_path,
                model="MVSep-Keys",
                output_dir=instrument_dir,
            )
            stems.update(keys_stems)
        except Exception as e:
            print(f"MVSep-Keys failed: {e}")
        
        # Strings
        try:
            strings_stems = self.client.separate(
                other_path,
                model="MVSep-Plucked-Strings",
                output_dir=instrument_dir,
            )
            stems.update(strings_stems)
        except Exception as e:
            print(f"MVSep-Strings failed: {e}")
        
        return stems
    
    def run_16_stem(
        self,
        input_path: Path,
        output_dir: Path,
    ) -> Dict[str, Path]:
        """Run full 16-stem separation pipeline.
        
        This chains Demucs (core 4) + MVSEP specialist models.
        Note: Requires Demucs to be installed separately for Stage 1.
        """
        from .separation import build_broad_stems
        
        # Stage 1: Core 4 stems (Demucs)
        broad_dir = ensure_dir(output_dir / "broad")
        broad_outputs, _, _, _ = build_broad_stems(
            input_path=input_path,
            job_root=output_dir,
            profile="quality",
            models=["mdx_extra", "htdemucs_ft"],
        )
        
        all_stems = {}
        
        # Stage 2A: Vocal sub-stems
        if "vocals" in broad_outputs:
            vocals_path = Path(broad_outputs["vocals"]["path"])
            vocal_substems = self.run_vocal_branch(vocals_path, output_dir)
            all_stems.update(vocal_substems)
        
        # Stage 2B: Drum sub-stems
        if "drums" in broad_outputs:
            drums_path = Path(broad_outputs["drums"]["path"])
            drum_substems = self.run_drum_branch(drums_path, output_dir)
            all_stems.update(drum_substems)
        
        # Stage 2C: Instrument sub-stems
        if "other" in broad_outputs:
            other_path = Path(broad_outputs["other"]["path"])
            instrument_substems = self.run_instrument_branch(other_path, output_dir)
            all_stems.update(instrument_substems)
        
        return all_stems
