import { useEffect, useEffectEvent, useState } from "react";

import { api, apiError, authHeaders } from "./api/client";
import {
  searchAudiusTracks,
  submitAudiusJob,
  submitUploadJob
} from "./features/separation/api";
import { formatDuration, importReason } from "./features/separation/format";
import { JobProgress } from "./features/separation/JobProgress";
import { ResultsPanel } from "./features/separation/ResultsPanel";
import type {
  AudiusTrack,
  Capabilities,
  JobPayload
} from "./features/separation/types";

const TERMINAL_STATES = new Set(["completed", "error", "failed", "cancelled"]);

function App() {
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [profile, setProfile] = useState("");
  const [inputMode, setInputMode] = useState<"upload" | "audius">("upload");
  const [file, setFile] = useState<File | null>(null);
  const [audiusQuery, setAudiusQuery] = useState("");
  const [audiusTracks, setAudiusTracks] = useState<AudiusTrack[]>([]);
  const [selectedTrack, setSelectedTrack] = useState<AudiusTrack | null>(null);
  const [searchingAudius, setSearchingAudius] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [job, setJob] = useState<JobPayload | null>(null);
  const [stage, setStage] = useState("Waiting for audio");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const refreshJob = useEffectEvent(async (jobId: string) => {
    try {
      const { data: payload, error: requestError, response } = await api.GET(
        "/jobs/{job_id}",
        {
          headers: authHeaders(),
          params: { path: { job_id: jobId } }
        }
      );
      if (requestError || !payload) throw apiError(requestError, response);
      setJob(payload);
      setStage(payload.stage || payload.status);
      if (TERMINAL_STATES.has(payload.status)) setBusy(false);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Status lookup failed");
      setBusy(false);
    }
  });

  useEffect(() => {
    let active = true;
    api.GET("/capabilities")
      .then(({ data, error: requestError, response }) => {
        if (requestError || !data) throw apiError(requestError, response);
        return data;
      })
      .then((payload) => {
        if (!active) return;
        setCapabilities(payload);
        setProfile(payload.evaluation_profile || payload.default_profile);
      })
      .catch((requestError: unknown) =>
        setError(requestError instanceof Error ? requestError.message : "Capabilities unavailable")
      );
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    const resumedJobId = new URLSearchParams(window.location.search).get("job");
    if (resumedJobId) {
      setBusy(true);
      refreshJob(resumedJobId);
    }
  }, []);

  useEffect(() => {
    if (!job?.job_id || TERMINAL_STATES.has(job.status)) return undefined;
    const timer = window.setInterval(() => refreshJob(job.job_id), 2000);
    return () => window.clearInterval(timer);
  }, [job?.job_id, job?.status]);

  const contract = capabilities?.product_contract;
  const selectedContract = String(capabilities?.profiles?.[profile]?.contract || "");
  const contractTargets = selectedContract
    ? capabilities?.stem_contracts?.[selectedContract]?.target_stems
    : undefined;
  const profileTargets = capabilities?.profiles?.[profile]?.target_stems;
  const supported = (
    Array.isArray(contractTargets)
      ? contractTargets
      : Array.isArray(profileTargets)
        ? profileTargets
        : []
  ).map(String);
  const pending = contract?.specialist_candidate_stems || [];
  const profiles = Object.entries(capabilities?.profiles || {}).filter(
    ([, metadata]) => metadata.public === true
  );
  const hasInput = inputMode === "upload" ? Boolean(file) : Boolean(selectedTrack);

  async function searchAudius(): Promise<void> {
    const query = audiusQuery.trim();
    if (query.length < 2) {
      setError("Enter at least two characters to search Audius");
      return;
    }
    setSearchingAudius(true);
    setError("");
    setSelectedTrack(null);
    try {
      const tracks = await searchAudiusTracks(query);
      setAudiusTracks(tracks);
      if (!tracks.length) setError("No downloadable Audius tracks matched this search");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Audius search failed");
    } finally {
      setSearchingAudius(false);
    }
  }

  async function start(): Promise<void> {
    if (!hasInput || !profile) return;
    setBusy(true);
    setError("");
    setJob(null);
    try {
      const payload =
        inputMode === "audius" && selectedTrack
          ? await submitAudiusJob(
              selectedTrack.id,
              profile,
              crypto.randomUUID(),
              setStage
            )
          : await submitUploadJob(file as File, profile, crypto.randomUUID(), setStage);
      setJob(payload);
      window.history.replaceState({}, "", `?job=${encodeURIComponent(payload.job_id)}`);
      await refreshJob(payload.job_id);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Job submission failed");
      setBusy(false);
    }
  }

  async function cancel(): Promise<void> {
    if (!job?.job_id) return;
    setStage("Requesting cancellation");
    try {
      const { data: payload, error: requestError, response } = await api.POST(
        "/jobs/{job_id}/cancel",
        {
          headers: authHeaders(),
          params: { path: { job_id: job.job_id } }
        }
      );
      if (requestError || !payload) throw apiError(requestError, response);
      setJob(payload);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Cancellation failed");
    }
  }

  function acceptFile(candidate: File | undefined): void {
    if (!candidate) return;
    setFile(candidate);
    setError("");
  }

  return (
    <div className="app-shell">
      <aside className="rail" aria-label="Primary">
        <div className="brand">SS</div>
        <nav>
          <a className="active" href="#new">New</a>
          <a href="#results">Jobs</a>
          <a href="#contract">Models</a>
        </nav>
        <span>v0.9</span>
      </aside>

      <main>
        <header className="hero">
          <div>
            <p className="eyebrow">Studio separation system</p>
            <h1>Pull the record apart.<br />Keep the music intact.</h1>
            <p className="lede">
              A hierarchical stem workspace for producers. Model support and release
              qualification are shown separately, so an output is never mistaken for proof.
            </p>
          </div>
          <section className="system-card" aria-live="polite">
            <small>System status</small>
            <strong>{error ? "Needs attention" : capabilities ? "Evaluation ready" : "Checking"}</strong>
            <p>{supported.length}-stem evaluation · status shown per job</p>
            <i className={error ? "status-dot status-dot--error" : "status-dot"} />
          </section>
        </header>

        <section className="work-grid" id="new">
          <div className="upload-panel">
            <p className="eyebrow eyebrow--lime">01 / Input</p>
            <h2>{inputMode === "upload" ? "Drop a track here" : "Find a licensed track"}</h2>
            <p>
              {inputMode === "upload"
                ? "WAV, FLAC, MP3, M4A or OGG · up to 500 MB"
                : "Search Audius · only derivative-friendly downloads can be imported"}
            </p>
            <div className="input-tabs" role="tablist" aria-label="Audio input source">
              <button
                role="tab"
                aria-selected={inputMode === "upload"}
                className={inputMode === "upload" ? "active" : ""}
                onClick={() => setInputMode("upload")}
              >
                Upload file
              </button>
              <button
                role="tab"
                aria-selected={inputMode === "audius"}
                className={inputMode === "audius" ? "active" : ""}
                onClick={() => setInputMode("audius")}
              >
                Audius catalog
              </button>
            </div>

            {inputMode === "upload" ? (
              <label
                className={`dropzone ${dragging ? "dropzone--active" : ""}`}
                onDragEnter={(event) => {
                  event.preventDefault();
                  setDragging(true);
                }}
                onDragOver={(event) => event.preventDefault()}
                onDragLeave={() => setDragging(false)}
                onDrop={(event) => {
                  event.preventDefault();
                  setDragging(false);
                  acceptFile(event.dataTransfer.files[0]);
                }}
              >
                <span>
                  <strong>{file?.name || "Choose audio or drag it into this panel"}</strong>
                  <small>
                    {file
                      ? `${(file.size / 1024 / 1024).toFixed(1)} MB`
                      : "No silent model fallback"}
                  </small>
                </span>
                <b>Choose file</b>
                <input
                  type="file"
                  accept=".flac,.m4a,.mp3,.ogg,.wav"
                  onChange={(event) => acceptFile(event.target.files?.[0])}
                />
              </label>
            ) : (
              <div className="audius-picker">
                <form
                  className="catalog-search"
                  onSubmit={(event) => {
                    event.preventDefault();
                    searchAudius();
                  }}
                >
                  <label htmlFor="audius-query">Search artist or track</label>
                  <div>
                    <input
                      id="audius-query"
                      value={audiusQuery}
                      maxLength={100}
                      onChange={(event) => setAudiusQuery(event.target.value)}
                      placeholder="Artist, song, or genre"
                    />
                    <button disabled={searchingAudius} type="submit">
                      {searchingAudius ? "Searching…" : "Search"}
                    </button>
                  </div>
                </form>
                {audiusTracks.length ? (
                  <div className="catalog-results" aria-label="Audius search results">
                    {audiusTracks.map((track) => (
                      <article
                        key={track.id}
                        className={`catalog-track ${
                          selectedTrack?.id === track.id ? "catalog-track--selected" : ""
                        }`}
                      >
                        {track.artwork_url ? (
                          <img src={track.artwork_url} alt="" loading="lazy" />
                        ) : (
                          <div className="artwork-placeholder" aria-hidden="true">♪</div>
                        )}
                        <div className="track-copy">
                          <strong>{track.title}</strong>
                          <small>
                            {track.artist} · {formatDuration(track.duration_seconds)}
                          </small>
                          <span>{track.license || "Licence unavailable"}</span>
                        </div>
                        <button
                          type="button"
                          disabled={!track.can_import}
                          onClick={() => setSelectedTrack(track)}
                        >
                          {track.can_import
                            ? selectedTrack?.id === track.id
                              ? "Selected"
                              : "Select"
                            : importReason(track.import_reason)}
                        </button>
                      </article>
                    ))}
                  </div>
                ) : (
                  <div className="catalog-empty">
                    Search results will show licence and import eligibility before selection.
                  </div>
                )}
              </div>
            )}
            <div className="submit-row">
              <label>
                Separation mode
                <select value={profile} onChange={(event) => setProfile(event.target.value)}>
                  {profiles.map(([name, metadata]) => (
                    <option key={name} value={name}>
                      {metadata.label}
                    </option>
                  ))}
                </select>
              </label>
              <button disabled={!hasInput || !profile || busy} onClick={start}>
                {busy
                  ? "Working…"
                  : inputMode === "audius"
                    ? "Import and split"
                    : "Start separation"}
              </button>
            </div>
          </div>

          <aside className="contract-card" id="contract">
            <p className="eyebrow eyebrow--lime">Current product contract</p>
            <h2>What this app can deliver</h2>
            <small>{supported.length}-stem evaluation output</small>
            <div className="stem-chips">
              {supported.map((stem) => <span key={stem}>{stem.replaceAll("_", " ")}</span>)}
            </div>
            <small className="pending-label">Specialist families · not released</small>
            <p>{pending.map((stem) => stem.replaceAll("_", " ")).join(" · ")}</p>
          </aside>
        </section>

        <JobProgress busy={busy} error={error} job={job} onCancel={cancel} stage={stage} />
        <ResultsPanel job={job} />
      </main>
    </div>
  );
}

export default App;
