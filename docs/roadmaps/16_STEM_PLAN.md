# 16-STEM PRO STANDARD PLAN
## Complete Implementation Roadmap for StemSplitter-Audio-Separation-Server

> **Note:** This is a historical research plan, not the current product
> quality claim. The current README claim is 8 quality-focused stems. Extra
> specialist stems remain experimental or coming soon until they pass smoke
> tests, benchmark scoring, and listening review.

**Historical goal:** Transform from 7 stems (5 pro, 2 DSP) to **16
pro-standard stems** using MVSEP and Demucs model chaining. This is not the
active product target. The active target is `quality_8_stems`.

**Timeline:** 2-3 weeks  
**Cost:** $0 (free tier) or ~$20/mo (MVSEP Pro)  
**GPU Required:** No (cloud processing via MVSEP API)

---

## 📊 CURRENT STATE vs TARGET

| Metric | Current | Target | Gap |
|--------|---------|--------|-----|
| **Total Stems** | 7 | **16** | +9 stems |
| **Pro-Grade Stems** | 5 | **16** | +11 stems |
| **DSP Filter Stems** | 7 (kick, snare, hats, etc.) | **0** | All replaced with AI |
| **Models Used** | 3 (Demucs only) | **10+** (Demucs + MVSEP) | +7 models |
| **Quality vs Leaders** | 80-85% of LALAL.AI | **90-95%** of AudioShake | Competitive |

---

## 🎯 THE 16-STEM TARGET

### **Core Stems (4) - Already Pro ✅**
| # | Stem | Model | Source | Status |
|---|------|-------|--------|--------|
| 1 | **Vocals** | MDX-Extra | Demucs | ✅ Current |
| 2 | **Drums** | HTDemucs-FT | Demucs | ✅ Current |
| 3 | **Bass** | HTDemucs-FT | Demucs | ✅ Current |
| 4 | **Other** | HTDemucs-FT | Demucs | ✅ Current |

---

### **Vocal Sub-Stems (3) - Need MVSEP**
| # | Stem | Model | Source | Priority |
|---|------|-------|--------|----------|
| 5 | **Lead Vocals** | BS-Roformer-V2 | MVSEP | P0 |
| 6 | **Backing Vocals** | UVR-BVE-Net or Kim_Vocal_2 | MVSEP | P1 |
| 7 | **Vocal Reverb** | UVR-De-Reverb-Echo | MVSEP | P2 |

---

### **Drum Sub-Stems (5) - Need MVSEP**
| # | Stem | Model | Source | Priority |
|---|------|-------|--------|----------|
| 8 | **Kick** | DrumSep / MVSep-Drums | MVSEP | P0 |
| 9 | **Snare** | DrumSep / MVSep-Drums | MVSEP | P0 |
| 10 | **Hi-Hats** | DrumSep / MVSep-Drums | MVSEP | P0 |
| 11 | **Cymbals** | DrumSep / MVSep-Drums | MVSEP | P1 |
| 12 | **Toms/Percussion** | DrumSep / MVSep-Drums | MVSEP | P1 |

---

### **Instrument Sub-Stems (4) - Need MVSEP**
| # | Stem | Model | Source | Priority |
|---|------|-------|--------|----------|
| 13 | **Piano** | MVSep-Piano or BS-Roformer-6stem | MVSEP | P0 |
| 14 | **Guitar** | MVSep-Lead-Guitar or BS-Roformer-6stem | MVSEP | P0 |
| 15 | **Keys/Synth** | MVSep-Keys / SCNet | MVSEP | P1 |
| 16 | **Strings** | MVSep-Plucked-Strings | MVSEP | P2 |

---

## 🏗️ ARCHITECTURE

### **Current Pipeline (Single-Pass)**
```
Original Track
     │
     ▼
┌─────────────────────────────┐
│ Demucs (3 models)           │
│ - MDX-Extra → Vocals        │
│ - HTDemucs-FT → Drums/Bass  │
│ - HTDemucs-6s → Piano/Gtr   │
└─────────────────────────────┘
     │
     ▼
7 Stems (5 pro, 2 good)
```

---

### **New Pipeline (Multi-Pass Chaining)**
```
Original Track
     │
     ▼
┌─────────────────────────────────┐
│ STAGE 1: Demucs (Core 4)        │
│ - MDX-Extra → Vocals            │
│ - HTDemucs-FT → Drums, Bass,    │
│                 Other           │
└─────────────────────────────────┘
     │
     ├──────────┬──────────┬──────┐
     ▼          ▼          ▼      ▼
┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
│Vocals  │ │Drums   │ │Bass    │ │Other   │
│(keep)  │ │(chain) │ │(keep)  │ │(chain) │
└────────┘ └────────┘ └────────┘ └────────┘
     │          │                       │
     ▼          ▼                       ▼
┌────────────┐ ┌─────────────┐  ┌──────────────┐
│STAGE 2A    │ │STAGE 2B     │  │STAGE 2C      │
│Vocal Branch│ │Drum Branch  │  │Instrument Br.│
│BS-Roformer │ │DrumSep      │  │MVSep Models  │
│- Lead Vox  │ │- Kick       │  │- Piano       │
│- Backing   │ │- Snare      │  │- Guitar      │
│- Reverb    │ │- Hats       │  │- Keys        │
└────────────┘ │- Cymbals    │  │- Strings     │
               │- Toms       │  └──────────────┘
               └─────────────┘

TOTAL: 16 Pro Stems
```

---

## 📅 IMPLEMENTATION TIMELINE

### **WEEK 1: Foundation + Vocal/Drum Branches**

#### **Day 1-2: MVSEP API Integration**
```python
# splitter/mvsep_client.py

import requests
from pathlib import Path
from typing import Dict

class MVSEPClient:
    """Client for MVSEP.com API."""
    
    BASE_URL = "https://mvsep.com/api/separate"
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key
        self.session = requests.Session()
    
    def separate(
        self,
        input_path: Path,
        model: str,
        output_dir: Path,
    ) -> Dict[str, Path]:
        """
        Separate audio using MVSEP specialist model.
        
        Args:
            input_path: Path to input audio file
            model: MVSEP model name (e.g., "BS-Roformer-V2", "DrumSep")
            output_dir: Directory to save output stems
        
        Returns:
            Dict mapping stem names to output file paths
        """
        with open(input_path, "rb") as f:
            response = self.session.post(
                self.BASE_URL,
                files={"audio": f},
                data={
                    "model": model,
                    "format": "wav",  # Free tier: mp3, Pro: wav/flac
                },
                timeout=300
            )
        
        response.raise_for_status()
        result = response.json()
        
        # Download and save stems
        stems = {}
        for stem_name, stem_url in result.get("stems", {}).items():
            stem_response = self.session.get(stem_url)
            stem_path = output_dir / f"{stem_name}.wav"
            stem_path.write_bytes(stem_response.content)
            stems[stem_name] = stem_path
        
        return stems
```

**Tests:**
- Test MVSEP API connectivity
- Test with sample vocal track → BS-Roformer-V2
- Test with sample drum track → DrumSep

---

#### **Day 3-4: Vocal Branch Integration**
```python
# splitter/specialist.py

from .mvsep_client import MVSEPClient

def build_vocal_substems(
    vocals_path: Path,
    job_root: Path,
) -> Dict[str, Dict[str, object]]:
    """Extract lead, backing, and reverb from vocals stem."""
    
    mvsep = MVSEPClient()
    vocal_dir = ensure_dir(job_root / "vocal_substems")
    derived = {}
    
    # Lead + Backing Vocals (BS-Roformer-V2)
    try:
        vocal_stems = mvsep.separate(
            vocals_path,
            model="BS-Roformer-V2",
            output_dir=vocal_dir,
        )
        
        if "lead_vocals" in vocal_stems:
            derived["lead_vocals"] = {
                "stem_name": "lead_vocals",
                "path": str(vocal_stems["lead_vocals"]),
                "parent_path": str(vocals_path),
                "source_model": "BS-Roformer-V2",
                "family": "vocals",
                "method": "mvsep_specialist",
            }
        
        if "backing_vocals" in vocal_stems:
            derived["backing_vocals"] = {
                "stem_name": "backing_vocals",
                "path": str(vocal_stems["backing_vocals"]),
                "parent_path": str(vocals_path),
                "source_model": "BS-Roformer-V2",
                "family": "vocals",
                "method": "mvsep_specialist",
            }
    except Exception as e:
        log_error(f"BS-Roformer failed: {e}")
    
    # Vocal Reverb (UVR-De-Reverb-Echo)
    try:
        reverb_stems = mvsep.separate(
            vocals_path,
            model="UVR-De-Reverb-Echo",
            output_dir=vocal_dir,
        )
        
        if "reverb" in reverb_stems:
            derived["vocal_reverb"] = {
                "stem_name": "vocal_reverb",
                "path": str(reverb_stems["reverb"]),
                "parent_path": str(vocals_path),
                "source_model": "UVR-De-Reverb-Echo",
                "family": "vocals",
                "method": "mvsep_specialist",
            }
    except Exception as e:
        log_error(f"De-Reverb failed: {e}")
    
    return derived
```

**Tests:**
- Test vocal sub-stem extraction on 10 songs
- Verify lead/backing separation quality
- Verify reverb isolation

---

#### **Day 5-7: Drum Branch Integration**
```python
# splitter/specialist.py

def build_drum_substems(
    drums_path: Path,
    job_root: Path,
) -> Dict[str, Dict[str, object]]:
    """Extract individual drum instruments from drums stem."""
    
    mvsep = MVSEPClient()
    drum_dir = ensure_dir(job_root / "drum_substems")
    derived = {}
    
    # DrumSep for individual drums
    try:
        drum_stems = mvsep.separate(
            drums_path,
            model="DrumSep",  # or "MVSep-Drums"
            output_dir=drum_dir,
        )
        
        drum_mapping = {
            "kick": "Kick",
            "snare": "Snare",
            "hi_hats": "Hi-Hats",
            "cymbals": "Cymbals",
            "toms": "Toms/Percussion",
        }
        
        for stem_key, stem_name in drum_mapping.items():
            if stem_key in drum_stems:
                derived[stem_key] = {
                    "stem_name": stem_key,
                    "path": str(drum_stems[stem_key]),
                    "parent_path": str(drums_path),
                    "source_model": "DrumSep",
                    "family": "drums",
                    "method": "mvsep_specialist",
                }
    except Exception as e:
        log_error(f"DrumSep failed: {e}")
    
    return derived
```

**Tests:**
- Test drum sub-stem extraction on 10 songs
- Verify kick/snare/hats separation quality
- Check for bleed between drum stems

---

### **WEEK 2: Instrument Branch + Integration**

#### **Day 8-10: Instrument Branch Integration**
```python
# splitter/specialist.py

def build_instrument_substems(
    other_path: Path,
    job_root: Path,
) -> Dict[str, Dict[str, object]]:
    """Extract individual instruments from 'other' stem."""
    
    mvsep = MVSEPClient()
    instrument_dir = ensure_dir(job_root / "instrument_substems")
    derived = {}
    
    # Piano (MVSep-Piano)
    try:
        piano_stems = mvsep.separate(
            other_path,
            model="MVSep-Piano",
            output_dir=instrument_dir,
        )
        
        if "piano" in piano_stems:
            derived["piano"] = {
                "stem_name": "piano",
                "path": str(piano_stems["piano"]),
                "parent_path": str(other_path),
                "source_model": "MVSep-Piano",
                "family": "piano",
                "method": "mvsep_specialist",
            }
    except Exception as e:
        log_error(f"MVSep-Piano failed: {e}")
    
    # Guitar (MVSep-Lead-Guitar)
    try:
        guitar_stems = mvsep.separate(
            other_path,
            model="MVSep-Lead-Guitar",
            output_dir=instrument_dir,
        )
        
        if "guitar" in guitar_stems:
            derived["guitar"] = {
                "stem_name": "guitar",
                "path": str(guitar_stems["guitar"]),
                "parent_path": str(other_path),
                "source_model": "MVSep-Lead-Guitar",
                "family": "guitar",
                "method": "mvsep_specialist",
            }
    except Exception as e:
        log_error(f"MVSep-Guitar failed: {e}")
    
    # Keys/Synth (MVSep-Keys or SCNet)
    try:
        keys_stems = mvsep.separate(
            other_path,
            model="MVSep-Keys",
            output_dir=instrument_dir,
        )
        
        if "keys" in keys_stems:
            derived["keys_synth"] = {
                "stem_name": "keys_synth",
                "path": str(keys_stems["keys"]),
                "parent_path": str(other_path),
                "source_model": "MVSep-Keys",
                "family": "keys",
                "method": "mvsep_specialist",
            }
    except Exception as e:
        log_error(f"MVSep-Keys failed: {e}")
    
    # Strings (MVSep-Plucked-Strings)
    try:
        strings_stems = mvsep.separate(
            other_path,
            model="MVSep-Plucked-Strings",
            output_dir=instrument_dir,
        )
        
        if "strings" in strings_stems:
            derived["strings"] = {
                "stem_name": "strings",
                "path": str(strings_stems["strings"]),
                "parent_path": str(other_path),
                "source_model": "MVSep-Plucked-Strings",
                "family": "strings",
                "method": "mvsep_specialist",
            }
    except Exception as e:
        log_error(f"MVSep-Strings failed: {e}")
    
    return derived
```

---

#### **Day 11-12: Full Pipeline Integration**
```python
# splitter/jobs.py

def run_job(job_id: str) -> None:
    """Run full 16-stem separation pipeline."""
    
    job_root = _job_root(job_id)
    status = get_job_status(job_id)
    input_path = Path(str(status["input_path"]))
    profile = str(status["profile"])
    profile_cfg = PROFILE_CONFIG[profile]
    
    try:
        # STAGE 1: Core 4 stems (Demucs)
        _update_status(job_root, status="running", stage="broad_split")
        broad_outputs, extended_candidates, run_info, missing = build_broad_stems(
            input_path, job_root, profile, profile_cfg["run_models"]
        )
        
        # STAGE 2A: Vocal sub-stems (MVSEP)
        if profile_cfg.get("vocal_substems", False) and "vocals" in broad_outputs:
            _update_status(job_root, stage="vocal_substems")
            vocals_path = Path(str(broad_outputs["vocals"]["path"]))
            vocal_substems = build_vocal_substems(vocals_path, job_root)
            broad_outputs.update(vocal_substems)
        
        # STAGE 2B: Drum sub-stems (MVSEP)
        if profile_cfg.get("drum_substems", False) and "drums" in broad_outputs:
            _update_status(job_root, stage="drum_substems")
            drums_path = Path(str(broad_outputs["drums"]["path"]))
            drum_substems = build_drum_substems(drums_path, job_root)
            broad_outputs.update(drum_substems)
        
        # STAGE 2C: Instrument sub-stems (MVSEP)
        if profile_cfg.get("instrument_substems", False) and "other" in broad_outputs:
            _update_status(job_root, stage="instrument_substems")
            other_path = Path(str(broad_outputs["other"]["path"]))
            instrument_substems = build_instrument_substems(other_path, job_root)
            broad_outputs.update(instrument_substems)
        
        # Continue with rest of pipeline (scoring, MIDI, packaging...)
        ...
        
    except Exception as e:
        _update_status(job_root, status="failed", error=str(e))
        raise
```

---

#### **Day 13-14: Testing + Quality Assurance**
```python
# tests/test_mvsep_integration.py

import pytest
from splitter.specialist import (
    build_vocal_substems,
    build_drum_substems,
    build_instrument_substems,
)

class TestMVSEPIntegration:
    """Test MVSEP specialist model integration."""
    
    def test_vocal_substems_extraction(self, tmp_path, sample_vocals):
        """Test lead/backing vocal separation."""
        result = build_vocal_substems(sample_vocals, tmp_path)
        
        assert "lead_vocals" in result
        assert "backing_vocals" in result
        assert Path(result["lead_vocals"]["path"]).exists()
        assert Path(result["backing_vocals"]["path"]).exists()
    
    def test_drum_substems_extraction(self, tmp_path, sample_drums):
        """Test individual drum separation."""
        result = build_drum_substems(sample_drums, tmp_path)
        
        assert "kick" in result
        assert "snare" in result
        assert "hi_hats" in result
        assert Path(result["kick"]["path"]).exists()
    
    def test_instrument_substems_extraction(self, tmp_path, sample_other):
        """Test instrument separation from 'other' stem."""
        result = build_instrument_substems(sample_other, tmp_path)
        
        assert "piano" in result or "guitar" in result
        assert Path(result.get("piano", result.get("guitar"))["path"]).exists()
```

---

### **WEEK 3: Benchmark + Polish**

#### **Day 15-17: Benchmark Suite**
```python
# splitter/benchmark.py

def run_16_stem_benchmark(corpus_path: Path, output_dir: Path):
    """Run benchmark on 16-stem pipeline."""
    
    from splitter.benchmark import BenchmarkRunner, BenchmarkSong
    
    # Load test corpus (MUSDB-HQ or custom)
    corpus = [
        BenchmarkSong(
            name="test_track_01",
            path=corpus_path / "test_track_01.wav",
            difficulty="mixed",
        ),
        # ... more tracks
    ]
    
    runner = BenchmarkRunner(corpus, output_dir)
    report = runner.run("16-stem-v1")
    
    # Key metrics to track:
    # - 16-stem success rate (% of stems successfully extracted)
    # - Avg quality score per stem family
    # - Processing time per stem
    # - MVSEP API failure rate
    
    print(f"Success Rate: {report.success_rate:.2%}")
    print(f"Avg Quality: {report.avg_broad_quality:.2f}")
```

---

#### **Day 18-19: Documentation + API Updates**
```markdown
# Update README.md

## Historical 16-Stem Pro Mode Draft

This obsolete draft must not be copied into the current README. StemSplitter
currently claims `quality_8_stems`; the 16-stem wording below was an
aspirational target before benchmark gates rejected several specialist
families.

### Core Stems (4)
- Vocals, Drums, Bass, Other

### Vocal Sub-Stems (3)
- Lead Vocals, Backing Vocals, Vocal Reverb

### Drum Sub-Stems (5)
- Kick, Snare, Hi-Hats, Cymbals, Toms/Percussion

### Instrument Sub-Stems (4)
- Piano, Guitar, Keys/Synth, Strings

### Usage

```bash
# Quality profile with 16-stem separation
curl -X POST http://localhost:5000/jobs \
  -F "file=@track.mp3" \
  -F "profile=quality_16stem"
```
"""
```

---

#### **Day 20-21: Final Testing + Deployment**
- Run full test suite
- Deploy to staging
- Test on 50 real songs
- Compare quality vs LALAL.AI/Fadr
- Deploy to production

---

## 💰 COST ANALYSIS

### **Option A: MVSEP Free Tier**
| Item | Cost | Limits |
|------|------|--------|
| MVSEP API | $0 | 50 separations/day, 10 min/song |
| Processing Time | ~15-20 min/song | Queue times may vary |
| Output Format | MP3 | WAV requires Pro |
| **Total** | **$0** | Good for testing |

---

### **Option B: MVSEP Pro**
| Item | Cost | Limits |
|------|------|--------|
| MVSEP Pro | ~$20/mo | Unlimited separations |
| Processing Time | ~5-10 min/song | Priority queue |
| Output Format | WAV/FLAC | Lossless quality |
| **Total** | **~$240/yr** | Production-ready |

---

### **Option C: Self-Hosted (Future)**
| Item | Cost | Requirements |
|------|------|--------------|
| Model Weights | $0 | Download from MVSEP/UVR5 |
| audio-separator | $0 | Python library |
| GPU Server | ~$100-300/mo | NVIDIA GPU (optional) |
| **Total** | **$0-300/mo** | Full control |

---

## 📈 QUALITY BENCHMARKS

### **Target Metrics (After Implementation)**

| Metric | Current | Target | Industry Leader |
|--------|---------|--------|-----------------|
| **Total Stems** | 7 | **16** | Fadr: 16 |
| **Pro-Grade Stems** | 5 | **16** | AudioShake: 8-10 |
| **Vocal SDR** | ~10 dB | **13+ dB** | AudioShake: 13.5 dB |
| **Drum SDR** | ~8 dB | **12+ dB** | LALAL.AI: 12 dB |
| **Instrument SDR** | ~7 dB | **11+ dB** | LALAL.AI: 11 dB |
| **Processing Time** | ~3 min | **~10 min** | LALAL.AI: ~2 min |

---

## 🔧 TECHNICAL REQUIREMENTS

### **Dependencies**
```python
# requirements.txt (additions)

requests>=2.31.0  # MVSEP API client
audio-separator>=0.5.0  # Optional: local model runner
```

### **Environment Variables**
```bash
# .env

MVSEP_API_KEY=  # Optional: for Pro tier
MVSEP_BASE_URL=https://mvsep.com/api/separate
MVSEP_MAX_RETRIES=3
MVSEP_TIMEOUT=300
```

---

## ✅ SUCCESS CRITERIA

### **Phase 1 Complete (Week 1)**
- [ ] MVSEP API client implemented
- [ ] Vocal sub-stems working (lead, backing)
- [ ] Drum sub-stems working (kick, snare, hats)
- [ ] Tests passing for vocal/drum branches

### **Phase 2 Complete (Week 2)**
- [ ] Instrument sub-stems working (piano, guitar, keys, strings)
- [ ] Full 16-stem pipeline integrated
- [ ] Manifest updated with all 16 stems
- [ ] Tests passing for full pipeline

### **Phase 3 Complete (Week 3)**
- [ ] Benchmark suite passing
- [ ] Quality metrics meet targets
- [ ] Documentation updated
- [ ] Deployed to production

---

## 🚨 RISKS + MITIGATIONS

| Risk | Impact | Mitigation |
|------|--------|------------|
| MVSEP API downtime | High | Implement retry logic, fallback to DSP |
| Queue times too long | Medium | Use Pro tier, cache results |
| Model quality inconsistent | Medium | Test each model, set quality thresholds |
| Cost overruns | Low | Monitor API usage, set daily limits |
| Output format (MP3 vs WAV) | Medium | Upgrade to Pro tier for production |

---

## 📝 POST-IMPLEMENTATION TODO

### **Future Enhancements (Post-16-Stem)**
1. **Lead/Backing Vocal Split** - UVR-BVE-Net integration
2. **Acoustic vs Electric Guitar** - MVSep-Guitar-Acoustic model
3. **Bass Guitar vs Synth Bass** - SCNet model
4. **Brass/Wind Instruments** - MVSep-Brass model
5. **Local Model Hosting** - Download weights, run with audio-separator
6. **GPU Acceleration** - CUDA support for faster processing

---

## 🎯 FINAL DELIVERABLE

**Historical target, not the current claim:**

✅ **16 pro-standard stems** (competitive with Fadr 16-stem)  
✅ **90-95% of AudioShake quality** at 1/10th the price  
✅ **Fully automated pipeline** (Demucs + MVSEP chaining)  
✅ **Benchmark suite** for quality tracking  
✅ **Production-ready code** with tests + docs  

The current implementation does not claim this deliverable. It claims 8
quality-focused stems and treats the remaining specialist families as
candidate, experimental, or coming-soon work.

**Total Cost:** $0 (free tier) or ~$20/mo (Pro tier)  
**Total Time:** 2-3 weeks  
**GPU Required:** No (cloud processing)

---

**Let's build this.** 🚀
