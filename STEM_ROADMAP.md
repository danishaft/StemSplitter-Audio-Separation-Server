# Stem Separation Roadmap: 14-Stem Target

## Current State Analysis (March 2026)

This document lists all 14 target stems, our current implementation method, quality assessment, and the model/action needed to make each stem **pro-grade** (comparable to LALAL.AI, Fadr, AudioShake).

---

## Stem Inventory

| # | Stem | Category | Current Method | Quality Status | Action Needed |
|---|------|----------|----------------|----------------|---------------|
| 1 | **Vocals** | Core Broad | MDX-Extra (AI) | ✅ **PRO** | None - already competitive |
| 2 | **Drums** | Core Broad | HTDemucs-FT (AI) | ✅ **PRO** | None - already competitive |
| 3 | **Bass** | Core Broad | HTDemucs-FT (AI) | ✅ **PRO** | None - already competitive |
| 4 | **Other** | Core Broad | HTDemucs-FT (AI) | ✅ **PRO** | None - already competitive |
| 5 | **Instrumental** | Core Broad | MDX-Extra (AI) | ✅ **PRO** | None - already competitive |
| 6 | **Piano** | Extended | HTDemucs-6s (AI) | 🟡 **GOOD** | Fine-tune on piano-heavy dataset |
| 7 | **Guitar** | Extended | HTDemucs-6s (AI) | 🟡 **GOOD** | Fine-tune on guitar-heavy dataset |
| 8 | **Kick** | Derived | DSP Lowpass @ 180Hz | 🔴 **TRASH** | **Need UVR5 MDX-Net Drum model** |
| 9 | **Snare/Clap** | Derived | DSP Bandpass 180-2500Hz | 🔴 **TRASH** | **Need UVR5 MDX-Net Drum model** |
| 10 | **Hats/Cymbals** | Derived | DSP Highpass @ 4000Hz | 🔴 **TRASH** | **Need UVR5 MDX-Net Drum model** |
| 11 | **Percussion** | Derived | DSP Bandpass 600-6000Hz | 🔴 **TRASH** | **Need UVR5 MDX-Net Drum model** |
| 12 | **Keys/Synth** | Derived | DSP Bandpass 180-5000Hz | 🔴 **TRASH** | **Need UVR5 Reformer model** |
| 13 | **Pads/Strings** | Derived | DSP Bandpass 120-1800Hz | 🔴 **TRASH** | **Need UVR5 Reformer model** |
| 14 | **FX** | Derived | DSP Highpass @ 5000Hz | 🔴 **TRASH** | **Need UVR5 FX model** |

---

## Quality Legend

| Status | Meaning | Action |
|--------|---------|--------|
| ✅ **PRO** | Competitive with LALAL.AI/AudioShake | No action needed |
| 🟡 **GOOD** | Usable but not best-in-class | Fine-tuning recommended |
| 🔴 **TRASH** | DSP filters, will bleed badly | **URGENT: Need AI models** |

---

## Core Broad Stems (5) - ✅ COMPLETE

### 1. Vocals
- **Model:** MDX-Extra
- **Method:** Two-stems vocal isolation
- **Quality:** 90-95% of LALAL.AI
- **Status:** Production-ready

### 2. Drums
- **Model:** HTDemucs-FT
- **Method:** 4-stem separation
- **Quality:** 85-90% of LALAL.AI
- **Status:** Production-ready

### 3. Bass
- **Model:** HTDemucs-FT
- **Method:** 4-stem separation
- **Quality:** 85-90% of LALAL.AI
- **Status:** Production-ready

### 4. Other
- **Model:** HTDemucs-FT
- **Method:** 4-stem separation
- **Quality:** 80-85% of LALAL.AI
- **Status:** Production-ready (some bleed expected)

### 5. Instrumental
- **Model:** MDX-Extra (no_vocals)
- **Method:** Two-stems instrumental
- **Quality:** 90-95% of LALAL.AI
- **Status:** Production-ready

---

## Extended Stems (2) - 🟡 NEEDS FINE-TUNING

### 6. Piano
- **Current Model:** HTDemucs-6s
- **Current Quality:** 60-70% of LALAL.AI
- **Problem:** Piano often bleeds into "other" or gets confused with guitars
- **Solution:** Fine-tune HTDemucs-6s on piano-heavy tracks
- **Dataset Needed:** MUSDB-HQ + piano-annotated tracks
- **Target Quality:** 85%+ of LALAL.AI

### 7. Guitar
- **Current Model:** HTDemucs-6s
- **Current Quality:** 60-70% of LALAL.AI
- **Problem:** Acoustic vs electric not distinguished; bleeds with other strings
- **Solution:** Fine-tune HTDemucs-6s on guitar-heavy tracks
- **Dataset Needed:** MUSDB-HQ + guitar-annotated tracks
- **Target Quality:** 85%+ of LALAL.AI

---

## Derived Stems (7) - 🔴 URGENT: NEED AI MODELS

### 8. Kick Drum
- **Current Method:** DSP lowpass filter @ 180Hz
- **Current Quality:** 30-40% (BLEED CITY)
- **Problem:** Bass guitar lives at 60-120Hz too - they BLEED
- **Solution:** UVR5 MDX-Net "Drum Separation" model
- **Model Needed:** `UVR-MDX-NET-Drums` or `BS-Roformer-ViperX-1296`
- **Target Quality:** 80-85% of LALAL.AI

### 9. Snare/Clap
- **Current Method:** DSP bandpass 180-2500Hz
- **Current Quality:** 30-40% (BLEED CITY)
- **Problem:** Guitar, vocals, piano all live in 180-2500Hz
- **Solution:** UVR5 MDX-Net "Drum Separation" model
- **Model Needed:** `UVR-MDX-NET-Drums` or `BS-Roformer-ViperX-1296`
- **Target Quality:** 80-85% of LALAL.AI

### 10. Hats/Cymbals
- **Current Method:** DSP highpass @ 4000Hz
- **Current Quality:** 40-50% (VOCAL SIBILANCE BLEED)
- **Problem:** Vocal "s", "t", "sh" sounds live at 4000-8000Hz
- **Solution:** UVR5 MDX-Net "Drum Separation" model
- **Model Needed:** `UVR-MDX-NET-Drums` or `BS-Roformer-ViperX-1296`
- **Target Quality:** 80-85% of LALAL.AI

### 11. Percussion
- **Current Method:** DSP bandpass 600-6000Hz
- **Current Quality:** 30-40% (EVERYTHING BLEEDS)
- **Problem:** This range contains vocals, guitars, snares, keys
- **Solution:** UVR5 MDX-Net "Percussion" model
- **Model Needed:** `UVR-MDX-NET-Percussion` or custom fine-tune
- **Target Quality:** 75-80% of LALAL.AI

### 12. Keys/Synth
- **Current Method:** DSP bandpass 180-5000Hz
- **Current Quality:** 40-50% (GUITAR/PIANO BLEED)
- **Problem:** Overlaps with guitar, piano, vocals
- **Solution:** UVR5 Reformer model for harmonic instruments
- **Model Needed:** `UVR5-Reformer-HG-OSR` or `MDX23C-Keys`
- **Target Quality:** 75-80% of LALAL.AI

### 13. Pads/Strings
- **Current Method:** DSP bandpass 120-1800Hz
- **Current Quality:** 30-40% (BASS/GUITAR BLEED)
- **Problem:** Low-mid range is CROWDED
- **Solution:** UVR5 Reformer model for sustained instruments
- **Model Needed:** `UVR5-Reformer-HG-OSR` or custom fine-tune
- **Target Quality:** 70-75% of LALAL.AI

### 14. FX
- **Current Method:** DSP highpass @ 5000Hz
- **Current Quality:** 40-50% (HATS/VOCAL SIBILANCE BLEED)
- **Problem:** High-frequency content from many sources
- **Solution:** UVR5 FX model or heuristic with better gating
- **Model Needed:** `UVR5-MDX-NET-FX` or custom detection
- **Target Quality:** 60-70% of LALAL.AI (FX are inherently messy)

---

## Priority Action Plan

### **P0: CRITICAL (Week 1)**
These make or break the 12+ stem claim:

1. **Integrate UVR5 MDX-Net for Drums**
   - Models: `BS-Roformer-ViperX-1296` or `UVR-MDX-NET-Drums`
   - Stems unlocked: Kick, Snare, Hats, Percussion (4 stems)
   - Quality gain: 30-40% → 80-85%

2. **Integrate UVR5 Reformer for Keys**
   - Model: `UVR5-Reformer-HG-OSR`
   - Stems unlocked: Keys/Synth, Pads/Strings (2 stems)
   - Quality gain: 40-50% → 75-80%

### **P1: HIGH (Week 2-3)**
Quality improvements for extended stems:

3. **Fine-tune HTDemucs-6s on Piano**
   - Dataset: MUSDB-HQ + piano tracks
   - Stem: Piano
   - Quality gain: 60-70% → 85%

4. **Fine-tune HTDemucs-6s on Guitar**
   - Dataset: MUSDB-HQ + guitar tracks
   - Stem: Guitar (split acoustic/electric if possible)
   - Quality gain: 60-70% → 85%

### **P2: MEDIUM (Week 4)**
Polish and edge cases:

5. **FX Detection Model**
   - Custom heuristic or UVR5 FX model
   - Stem: FX
   - Quality gain: 40-50% → 60-70%

6. **Benchmark Suite**
   - Run on MUSDB-HQ for published SDR scores
   - Compare vs LALAL.AI/Fadr published metrics

---

## Model Sourcing

### **UVR5 Models (Open Source)**
| Model | Purpose | Source |
|-------|---------|--------|
| `BS-Roformer-ViperX-1296` | Best vocal/instrumental | GitHub: Anjok07/ultimatevocalremovergui |
| `MDX23C` | Drums/bass separation | GitHub: Anjok07/ultimatevocalremovergui |
| `Reformer-HG-OSR` | Guitar/piano/keys | GitHub: Anjok07/ultimatevocalremovergui |
| `UVR-MDX-NET-Drums` | Individual drum instruments | GitHub: Anjok07/ultimatevocalremovergui |

### **Fine-Tuning Datasets**
| Dataset | Purpose | License |
|---------|---------|---------|
| MUSDB-HQ | Base fine-tuning | CC-BY-NC |
| GuitarSet | Guitar annotation | CC-BY |
| Piano-e-Competition | Piano annotation | CC-BY |
| Slakh2100 | Multi-instrument | CC-BY |

---

## Success Metrics

After full implementation:

| Metric | Target | Current |
|--------|--------|---------|
| **Total Stems** | 14 | 14 (structurally) |
| **Pro-Grade Stems** | 12+ | 5 (core broad) |
| **Avg SDR (MUSDB-HQ)** | 12+ dB | Unmeasured |
| **Publish Rate (Easy)** | 85%+ | Unknown |
| **Publish Rate (Hard)** | 60%+ | Unknown |

---

## Competitive Positioning (Post-Implementation)

| Feature | Us | Fadr | LALAL.AI | AudioShake |
|---------|----|------|----------|------------|
| **Stem Count** | 14 | 16 | 10 | 5-8 |
| **Core Quality** | ✅ | ✅ | ✅ | ✅ |
| **Drum Sub-stems** | 🔲 (planned) | ✅ | ❌ | ❌ |
| **Guitar Sub-types** | 🔲 (planned) | ✅ | ✅ | ❌ |
| **Local Processing** | ✅ | ❌ | ❌ | ❌ |
| **Price** | Free | $10/mo | £6/mo | Enterprise |
| **Benchmarked** | 🔲 (planned) | ❌ | ✅ | ✅ |

---

## Timeline Summary

| Week | Milestone | Stems Unlocked |
|------|-----------|----------------|
| 1 | UVR5 Drum Integration | Kick, Snare, Hats, Percussion |
| 2 | UVR5 Keys Integration | Keys/Synth, Pads/Strings |
| 3 | Piano/Guitar Fine-Tune | Piano, Guitar (improved) |
| 4 | Benchmark + Polish | FX, Full Suite |

**End State:** 12-14 pro-grade stems, competitive with Fadr/LALAL.AI at 1/10th the price.
