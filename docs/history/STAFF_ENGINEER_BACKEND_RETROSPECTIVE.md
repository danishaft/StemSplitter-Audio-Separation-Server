# Staff Engineer Backend Retrospective — StemSplitter

**Author of review:** Claude (staff-engineer lens, drawn from Suno / Spotify / Moises-class audio ML platforms)
**Repo:** `StemSplitter-Audio-Separation-Server`
**Date:** 2026-07-31
**Status:** Retrospective report — narrative plus part-by-part engineering diff

---

## Scope and method

This is a backend retrospective written against the code as it actually is, not as
marketed. I read the operationally meaningful surface before judging:

- `splitter/config.py` (561 LOC) — the entire configuration and product-contract surface
- `splitter/separation.py` (249 LOC) — broad/derived stem construction, DSP fallbacks
- `splitter/infrastructure/dispatch.py` (157 LOC) — thread + RQ dispatchers
- `splitter/api/app.py` (146 LOC) — FastAPI wiring, middleware, error model
- `splitter/infrastructure/job_store.py` (783 LOC) — the durable job authority
- `splitter/jobs.py` (1,405 LOC) — the job execution orchestration
- `workers/audio_separator_gpu_worker.py` — the GPU inference worker
- `models/registry.yaml` + `models/product_12_stem_contract.yaml` — machine-readable contracts
- `README.md`, `.gitignore`, `Makefile`, `requirements/*`, `uv.lock`
- **Ran the full backend suite: 105 passed, 7 skipped** (skips are integration tests
  correctly gated behind `MVSEP_API_KEY` / GPU credentials)

The reference set is grounded in how the systems that actually matter are built:

- **Open source:** Demucs (Meta), Spleeter (Deezer), Open-Unmix (SigSep), AudioSep (Meta),
  UVR5 (Apashe), MVSEP / separation-fork MDX, BandIt / SRoFormer (Meta/Stanford)
- **Closed, professional:** Suno stem engine, Moises, Lalal.ai, iZotope RX, Acon
  Acoustica, Serato / BandLab stems

Notably, this repo vendored the SOTA open systems into `external_repos/` as live
comparators (`AudioSep`, `bandit`, `MVSEP-CDX23`, `xlance-msr`, `unified-source-separation`,
`cocktail-fork-separation`…). The author *studied* the reference architectures. The review
therefore distinguishes between what was **adopted well**, what was **reinvented**, and
what was **studied but not yet applied**.

---

## Executive summary

> This is not typical "first music app" code. Reading it is like reading someone who has
> shipped durable async ML job systems at a serious company: explicit state machines,
> lease-based workers, outbox dispatch, contract-driven capability surfaces, real
> benchmarks against the SOTA, and — rarest of all — honest release-status documentation.

The architecture is **above-average for the domain and genuinely staff-grade in the
orchestration and quality-verification layers.** The single product-defining gap is the
**model-serving layer**: how models are *actually executed at scale*. Almost everything
downstream of "choose a good model" — subprocess inference, fp32 precision, no continuous
batching, no persistent model server, no quantization — is exactly the boundary that
separates a research/architecture platform from a Moises/Suno-class product.

| Dimension | Score /10 | Verdict |
|---|---|---|
| Job orchestration (control plane) | 9 | Staff-grade — the strongest layer |
| Quality verification & benchmarking | 8.5 | Senior, near-staff |
| Engine model selection & analysis breadth | 8 | Senior (beyond most pro systems) |
| Maintainability & engineering discipline | 8 | Verified passing suite, strong CI, honesty |
| Security hardening | 7.5 | Good; env gitignored, verified |
| Abstraction hygiene (YAGNI) | 6 | Over-abstracted; dev backends kept past need |
| Inference serving & GPU economics | 4 | Junior — the product gap |
| **Overall** | **7.5–8** | **Would hire. The serving layer is the fix.** |

---

## Part 1 — Part-by-part engineering diff

Scoring convention: `[good]` / `[weak]` / `[missing]` / `[over-abstracted]` / `[junior]`

### 1.1 The separation engine itself

| Concept | Reference | StemSplitter | Verdict |
|---|---|---|---|
| Base model selection | Demucs `htdemucs`/`mdx_extra`/`htdemucs_6s`, MDX-Net VRAM variants, BS-Roformer | Same SOTA mix + UVR specialist checkpoints (`local_model_registry`) | **good** |
| Engine runtime | Pro: persistent Triton/ONNX serving, in-process, warm pools | `audio-separator` / `audiosep` invoked via **subprocess** | **junior** — the crux |
| Model caching | Cache + quantize + half-precision + dynamic batch | `AUDIO_SEPARATOR_MODEL_CACHE=1`, cache dir, `SEPARATOR_CACHE` | **weak** — caches weights, doesn't manage serving |
| GPU fleet topology | Moises/Suno: model-specialized autoscaled workers | Modal workers, per-profile GPU (T4/L4), branch tiering, specialist per model family | **good** |
| VRAM/throughput econ | Quant fp16, batch, smallest-fitting GPU | `unit_economics.py` + `benchmarks/gpu_bakeoff/` exist | **good intent / weak evidence** |
| Continuous batching | Pro serving | `GPU_WORKER_MAX_CONCURRENCY=1`, `sequential` mode | **missing** |
| Long-form / chunked audio | RX, Acon, chunked Demucs for >6-min | whole-file subprocess | **weak** |
| MIDI / pitch / key / tempo / sections | rare even in pro tools | `analysis.py` full music-analysis parity (audio2midi, tempo, key, sections) | **very good** — the differentiator |

**1.1 verdict:** model *selection* and *analysis breadth* are senior; **model *serving* is the
most junior part of the entire repo.** Subprocess-per-job, fp32, no batching. This is the
boundary between "Audacity plugin with good models" and "product."

---

### 1.2 Async job orchestration (control plane)

The strongest layer. `splitter/infrastructure/job_store.py` models this correctly:

| Concept | Reference | StemSplitter | Verdict |
|---|---|---|---|
| Durable state machine | pro: DB-backed, explicit transitions | `JOB_TRANSITIONS` (job_store.py:15) — real FSM | **excellent** |
| Transactional dispatch outbox | standard at scale | `claim_dispatches` / `mark_dispatched` | **excellent** — staff-grade |
| Worker leases + renewal | pro lease on long inference | `acquire/renew/release_lease` + `list_reconcilable` | **excellent** |
| Idempotency for retries | required | `idempotency_key`, `.idempotency.json` | **good** |
| Durable event log | rarely done | ordered per-job `events.json`, `list_events` | **over-engineering-but-correct** |
| Retry / backoff | — | `JOB_RETRY_INTERVALS`, `max_attempts`, RQ `Retry` | **good** |
| Worker auth | token + HMAC / mTLS | HMAC + API key on worker | **good** |
| **Backend abstraction surface** | one real backend at a time | `JobStore(Protocol)` × JSON/Postgres; `JobDispatcher` × thread/RQ | **over-abstracted** (see §1.6) |

**1.2 verdict:** the state machine + outbox + leases + idempotency + reconciliation combo
**is* the durable-job pattern Suno/Moises run. Reconstruction of this pattern, from study, is
the strongest signal in the repo.

---

### 1.3 Inference serving & cost — where money is actually spent

The weakest layer, and the one that decides the *business*.

| Concept | Reference | StemSplitter | Verdict |
|---|---|---|---|
| Quantized inference (fp16/INT8) | all pro | fp32 throughout `separation.py` | **missing** |
| Continuous batching | pro serving | max_concurrency=1, sequential | **missing** |
| Model warm pool / multiplexer | pro serving | `SEPARATOR_CACHE` (start) but subprocess spawn per job | **weak** |
| Autoscale-to-queue-depth | pro | Modal keep-warm params exist | **good** |
| GPU type per profile | — | T4 / L4 / RTX per profile | **good** |
| Cold-start latency | pro prewarm snapshot | Modal cold boot, uncached first call | **weak** |
| **Cost as a release gate** | pro treat unit econ as gating | `unit_economics.py` exists but does **not** gate release | **missing-gate** |

**1.3 verdict:** the repo is written as if GPU compute is free. At Moises/Suno, per-song GPU
cost is a core metric; here it is a module that documents intent without enforcing it.
`max_workers=1` + subprocess + fp32 would make per-song cost unacceptable at product scale.

---

### 1.4 Output quality verification (the audio reviewer's core concern)

Senior, near-staff. The closest to a real audio team in the whole repo.

| Concept | Reference | StemSplitter | Verdict |
|---|---|---|---|
| Objective metric vs ground truth | SDR/SIR/SAR, SI-SDR, Kim/mel-bandit vocals metric | `models/stem_qualification.yaml`, `ground_truth.py`, confidence scores, `scoring.py` band rules | **excellent** |
| Independent benchmark harness | UVR community; pro blind evals | `benchmarks/` — audiosep, comparators, golden_path, sota_candidates, mvsep_mega53, reliability, load, hatchet | **excellent** — more than most companies |
| Follows the literature | — | vendored AudioSep/bandit/MVSEP-CDX23/xlance as live comparators | **excellent** |
| Ground-truth corpus | pro: many hours curated | "30-song ground-truth benchmark unfinished" (README) | **weak** |
| Human / listening eval | pro: mandatory | not present | **junior at product level** |

**1.4 verdict:** great benchmarks + honest qualification state. The one gap — finished
ground truth + a listening gate — is exactly what makes the metrics trustworthy enough to
release on.

---

### 1.5 Security & production hardening

| Concept | Reference | StemSplitter | Verdict |
|---|---|---|---|
| Trusted hosts / CORS allowlist / rate limits | — | config-driven, `EdgePolicyMiddleware`, shared rate namespace | **good** |
| Auth | JWT JWKS; worker HMAC | yes | **good** |
| Presigned out-of-band uploads | pro pattern | `/uploads` → presigned private storage | **good** |
| Secrets out of git | must be none | `.env.local` / `.env.*.local` **gitignored** (verified, `.gitignore:14-15`), files `600` | **good — verified** |
| Bomb / content guards | pro: strict | `MAX_CONTENT_LENGTH`, allowed ext, md5, size caps | **good** |
| Licensing / abuse / fair-use | DMCA + licensing + access control | `allow_noncommercial_licenses=0` default, Audius license gate | **good — better than most** |
| Supply-chain checks | — | CodeQL, dependency-review, Trivy in CI | **good** |

**1.5 verdict:** solid for an indie/startup. The env-file concern is resolved (gitignored).

---

### 1.6 Engineering discipline, DX, and abstraction hygiene

| Concept | Reference | StemSplitter | Verdict |
|---|---|---|---|
| Test suite runs & passes | — | **105 passed, 7 skipped** (executed) | **excellent** — rare for this domain |
| Tests gated by env keys | — | MVSEP/GPU integration correctly skipped | **good** |
| Typing where it matters | — | `Protocol`, `dataclass`, `Mapping` | **good** |
| Reproducible deps | — | `uv.lock` (429 KB), `requirements.lock` | **excellent** |
| CI breadth | — | ruff, frontend build, container, Bicep/Terraform, CodeQL, Trivy | **excellent** |
| Docs / runbooks | — | `docs/` architecture, operations, research, `ENGINEERING_LOG.md` | **excellent** |
| Release-status honesty | — | "evaluation profile, not a production-quality claim" | **excellent** |

**Abstraction hygiene — the honest critique:**
- **Four job-store/dispatch backends, two dev-only, behind `Protocol`s before scale justified
  a second.** The Protocol shape is correct; the *count* of live implementations is premature.
- **`PROFILE_CONFIG` carries five profiles**, of which ~two are actually public
  (`quality_gpu_experimental`, legacy `preview`). The experimental/fallback tree adds branch
  surface ahead of demand.
- **File geometry contradicts the clean layering.** The hexagon is right in principle, but:
  - `splitter/jobs.py` = **1,405 LOC** (orchestration, GPU client, specialist dispatch,
    scoring, MIDI, packaging co-habiting)
  - `splitter/infrastructure/job_store.py` = **783 LOC**
  - These two god-files will resist the coming modeling work. Split orchestration from
    engine invocation before hitting 3k LOC.

---

## Part 2 — The retrospective narrative (the "what would I tell the author" part)

### What went right (keep doing this)
1. **You built the right bones for a durable async system before you needed them.**
   State machine, outbox, leases, idempotency, reconciliation. Most real products bolt this
   on later and regret it.
2. **You studied the actual SOTA and vendored it as a comparator.** That is the correct,
   humble way to build in this field, and most shops skip it.
3. **You made the product contract machine-readable** (`models/*.yaml`) and separated
   *release gate for the architecture* from *release gate for model quality*. That honesty
   is worth more than the architecture.
4. **You have real quality verification** — more benchmark harness than most companies
   ship. It keeps you honest.

### What to fix first (the product-defining gap)
5. **The serving layer is the whole product gap.** Replace subprocess-per-job inference
   with an **in-process, batched, warm-model GPU server**:
   - Hold the model in memory in a persistent process (no subprocess spawn per job).
   - Track `binary_recompute`/ONNX or fp16 running engines; add **fp16 + optional INT8**.
   - Enable **continuous batching** across jobs on a worker (raise
     `GPU_WORKER_MAX_CONCURRENCY`, add a queue-depth autoscaler).
   - Chunk long-form audio with overlap-and-crossfade for >6-min inputs.
   This is the single change that moves this repo from "research platform" to "product."
6. **Make unit economics a release gate, not a diagnostic.** `unit_economics.py` should
   *fail a job profile* when predicted per-song GPU cost exceeds budget. Until then the
   business reviewers (the people whose sign-off you need) have no number to trust.

### What to finish (the quality gap)
7. **Finish the 30-song ground-truth benchmark and add a blind listening gate.** Metrics
   without ears are how you ship an 11-stem profile where `synth` bleeds. A 3-reviewer
   forced-choice blind eval against `htdemucs_6s` on your target stems is cheap and is the
   difference between "we think it's good" and "it's good."

### What to delete (YAGNI / over-abstraction)
8. **Delete the dev-only backends once Postgres+Redis are wired in CI.** Keep the `Protocol`s
   (they're the right shape); collapse the JSON store and thread dispatcher to a single
   documented development path. Fewer live branches = fewer places for a subtle
   dev-prod divergence to hide.
9. **Prune `PROFILE_CONFIG` to the profiles you ship** (public + one evaluation). Move the
   experimental/fallback tree into `experiments/` instead of the runtime config.
10. **Split `jobs.py` and `job_store.py`** along the orchestration/engine boundary before
    they grow further.

---

## Part 3 — What a Suno/Spotify-audio-staff reviewer would say in one paragraph

> Above-average architecture for the domain, genuinely senior in durable job orchestration
> and quality verification, honest about release status — I'd hire this person. But the model
> **serving** layer — subprocess inference, fp32, no continuous batching, no warm loader — is
> the entire gap between "a great research/architecture platform" and "a product that costs
> acceptable dollars per song at scale." Fix that, make unit economics a gate, finish the
> ground truth plus a listening eval, and delete a few dev-only abstractions. Then this is a
> ship-able music platform.

---

## Appendix — raw evidence referenced

- `JOB_TRANSITIONS` state machine: `splitter/infrastructure/job_store.py:15-24`
- Outbox: `claim_dispatches` / `mark_dispatched` / `mark_dispatch_failed` (job_store.py:67-83)
- Protocols: `JobStore`, `JobDispatcher` (job_store.py:32, dispatch.py:17)
- Profile capability tree + fallbacks: `splitter/config.py:250-306`
- Subprocess Demucs: `splitter/separation.py:52-74`
- Derived-stem DSP heuristics: `DERIVED_STEM_RULES`, `splitter/config.py:183-195`
- GPU worker engine wiring: `workers/audio_separator_gpu_worker.py` (SEPARATOR_CACHE, sequential mode)
- Machine-readable contracts: `models/registry.yaml`, `models/product_12_stem_contract.yaml`
- Honest limits: `README.md`, "Known limits" section
- Test status: `105 passed, 7 skipped` (executed 2026-07-31)
- Env hygiene: `.gitignore:14-15` (`.env.local`, `.env.*.local`)
