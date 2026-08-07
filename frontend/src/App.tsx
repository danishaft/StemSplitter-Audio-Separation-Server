import { useEffect, useEffectEvent, useState } from "react";

import { api, apiError, authHeaders } from "./api/client";
import {
  searchAudiusTracks,
  submitAudiusJob,
  submitUploadJob
} from "./features/separation/api";
import { Icon } from "./features/separation/Icon";
import { JobProgress } from "./features/separation/JobProgress";
import { LandingStory } from "./features/separation/LandingStory";
import { ProfilePicker } from "./features/separation/ProfilePicker";
import { ResultsPanel } from "./features/separation/ResultsPanel";
import { SourcePicker } from "./features/separation/SourcePicker";
import { StudioHeader } from "./features/separation/StudioHeader";
import type {
  AudiusTrack,
  Capabilities,
  JobPayload
} from "./features/separation/types";

const MAX_UPLOAD_BYTES = 500 * 1024 * 1024;
const SUPPORTED_FILE = /\.(flac|m4a|mp3|ogg|wav)$/i;
const TERMINAL_STATES = new Set(["completed", "error", "failed", "cancelled"]);

function App() {
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [capabilitiesState, setCapabilitiesState] = useState<"loading" | "ready" | "error">("loading");
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
  const [sourceNotice, setSourceNotice] = useState("");
  const [jobError, setJobError] = useState("");
  const [systemError, setSystemError] = useState("");
  const [busy, setBusy] = useState(false);
  const [connectionIssue, setConnectionIssue] = useState(false);

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
      setConnectionIssue(false);
      setJobError("");
      if (TERMINAL_STATES.has(payload.status)) setBusy(false);
    } catch (requestError) {
      setJobError(
        requestError instanceof Error
          ? requestError.message
          : "We could not refresh this job. Your uploaded work is still safe."
      );
      setConnectionIssue(true);
    }
  });

  async function loadCapabilities(): Promise<void> {
    setCapabilitiesState("loading");
    setSystemError("");
    try {
      const { data, error: requestError, response } = await api.GET("/capabilities");
      if (requestError || !data) throw apiError(requestError, response);
      setCapabilities(data);
      setProfile(data.recommended_profile || data.evaluation_profile || data.default_profile);
      setCapabilitiesState("ready");
    } catch {
      setCapabilities(null);
      setProfile("");
      setCapabilitiesState("error");
      setSystemError("The studio service is unavailable. Retry after the API reconnects.");
    }
  }

  useEffect(() => {
    void loadCapabilities();
  }, []);

  useEffect(() => {
    const resumedJobId = new URLSearchParams(window.location.search).get("job");
    if (resumedJobId) {
      setBusy(true);
      setStage("Reconnecting to your session");
      refreshJob(resumedJobId);
    }
  }, []);

  useEffect(() => {
    if (!job?.job_id || TERMINAL_STATES.has(job.status)) return undefined;
    const timer = window.setInterval(() => refreshJob(job.job_id), 2000);
    return () => window.clearInterval(timer);
  }, [job?.job_id, job?.status]);

  const contract = capabilities?.product_contract;
  const profileMetadata = capabilities?.profiles?.[profile];
  const selectedContract = String(profileMetadata?.contract || "");
  const contractTargets = selectedContract
    ? capabilities?.stem_contracts?.[selectedContract]?.target_stems
    : undefined;
  const metadataTargets = profileMetadata?.target_stems;
  const supported = (
    Array.isArray(contractTargets)
      ? contractTargets
      : Array.isArray(metadataTargets)
        ? metadataTargets
        : contract?.model_supported_stems || []
  ).map(String);
  const pending = contract?.specialist_candidate_stems || [];
  const hasInput = inputMode === "upload" ? Boolean(file) : Boolean(selectedTrack);
  const sourceName = inputMode === "upload"
    ? file?.name
    : selectedTrack ? `${selectedTrack.title} · ${selectedTrack.artist}` : undefined;

  async function searchAudius(): Promise<void> {
    const query = audiusQuery.trim();
    if (query.length < 2) {
      setSourceNotice("Enter at least two characters to search Audius.");
      return;
    }
    setSearchingAudius(true);
    setSourceNotice("");
    setSelectedTrack(null);
    try {
      const tracks = await searchAudiusTracks(query);
      setAudiusTracks(tracks);
      if (!tracks.length) {
        setSourceNotice("No downloadable Audius tracks matched this search. Try an artist or a shorter title.");
      }
    } catch (requestError) {
      setSourceNotice(
        requestError instanceof Error
          ? requestError.message
          : "Audius search is unavailable. Your upload option still works."
      );
    } finally {
      setSearchingAudius(false);
    }
  }

  async function start(): Promise<void> {
    if (!hasInput || !profile) return;
    setBusy(true);
    setConnectionIssue(false);
    setSourceNotice("");
    setJobError("");
    setJob(null);
    setStage("Preparing your session");
    window.requestAnimationFrame(() => {
      document.getElementById("job-status")?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
    try {
      const payload = inputMode === "audius" && selectedTrack
        ? await submitAudiusJob(selectedTrack.id, profile, crypto.randomUUID(), setStage)
        : await submitUploadJob(file as File, profile, crypto.randomUUID(), setStage);
      setJob(payload);
      window.history.replaceState({}, "", `?job=${encodeURIComponent(payload.job_id)}`);
      await refreshJob(payload.job_id);
    } catch (requestError) {
      setJobError(
        requestError instanceof Error
          ? requestError.message
          : "We could not start the split. Your local file has not been changed."
      );
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
      setJobError(
        requestError instanceof Error
          ? requestError.message
          : "Cancellation did not reach the server. Check the job status before trying again."
      );
    }
  }

  function acceptFile(candidate: File | undefined): void {
    if (!candidate) return;
    if (!SUPPORTED_FILE.test(candidate.name)) {
      setFile(null);
      setSourceNotice("Choose a WAV, FLAC, MP3, M4A, or OGG audio file.");
      return;
    }
    if (candidate.size > MAX_UPLOAD_BYTES) {
      setFile(null);
      setSourceNotice("This file is larger than 500 MB. Export a smaller audio file and try again.");
      return;
    }
    setFile(candidate);
    setSourceNotice("");
  }

  function changeInputMode(mode: "upload" | "audius"): void {
    setInputMode(mode);
    setSourceNotice("");
  }

  return (
    <div className="app-shell" id="top">
      <StudioHeader
        hasSession={job?.status === "completed"}
      />

      <main className={job?.status === "completed" ? "main--workspace" : "main--landing"}>
        {job?.status !== "completed" ? (
        <section className="studio-reveal" id="studio" aria-labelledby="studio-title">
        <header className="studio-intro">
          <div>
            <p className="eyebrow">Inside the studio</p>
            <h2 id="studio-title">The song stays whole while the parts open up.</h2>
          </div>
          <p>Bring in a track, choose the separation depth, and listen from the same place as each output becomes ready.</p>
        </header>
        {systemError ? (
          <div className="system-notice" role="status">
            <span>{systemError}</span>
            <button onClick={loadCapabilities} type="button">Retry connection</button>
          </div>
        ) : null}
        <div className="studio" aria-label="New separation session">
          <div className="studio__main">
            <SourcePicker
              audiusQuery={audiusQuery}
              audiusTracks={audiusTracks}
              dragging={dragging}
              file={file}
              inputMode={inputMode}
              onAcceptFile={acceptFile}
              onAudiusQueryChange={setAudiusQuery}
              onDraggingChange={setDragging}
              onInputModeChange={changeInputMode}
              onSearchAudius={searchAudius}
              onSelectTrack={(track) => {
                setSelectedTrack(track);
                setSourceNotice("");
              }}
              searchingAudius={searchingAudius}
              selectedTrack={selectedTrack}
              notice={!job && !busy ? sourceNotice : ""}
            />

            <div className="profile-section">
              <div className="section-heading">
                <div>
                  <p className="eyebrow">Method</p>
                  <h2>Choose the separation depth</h2>
                </div>
              </div>
              <ProfilePicker
                availability={capabilitiesState}
                capabilities={capabilities}
                disabled={busy}
                onChange={setProfile}
                profile={profile}
              />
            </div>

            <div className="session-submit">
              <div>
                <small>Session source</small>
                <strong>{sourceName || "No track selected"}</strong>
              </div>
              <button disabled={!hasInput || !profile || busy} onClick={start} type="button">
                {busy ? "Separation in progress" : inputMode === "audius" ? "Import and separate" : "Start separation"}
                <Icon name="arrow" size={19} />
              </button>
            </div>
          </div>

          <aside className="contract-card" aria-labelledby="contract-title">
            <p className="eyebrow">Release contract</p>
            {capabilitiesState === "ready" ? (
              <>
                <h2 id="contract-title">Hear what is ready. See what is not.</h2>
                <p className="contract-card__intro">
                  Your chosen profile lists every intended stem. Only clear, usable results reach the session.
                </p>
                <div className="stem-list">
                  {supported.map((stem, index) => (
                    <div key={stem}>
                      <span>{String(index + 1).padStart(2, "0")}</span>
                      <strong>{stem.replaceAll("_", " ")}</strong>
                      <Icon name="check" size={17} />
                    </div>
                  ))}
                </div>
                {pending.length ? (
                  <div className="contract-card__pending">
                    <small>Optional stems, released only when clear</small>
                    <p>{pending.map((stem) => stem.replaceAll("_", " ")).join(" · ")}</p>
                  </div>
                ) : null}
              </>
            ) : capabilitiesState === "loading" ? (
              <>
                <h2 id="contract-title">Checking the available outputs.</h2>
                <p className="contract-card__intro">
                  The studio is loading profiles and stem details for this session.
                </p>
              </>
            ) : (
              <>
                <h2 id="contract-title">Output details are unavailable.</h2>
                <p className="contract-card__intro">
                  Reconnect to review available profiles and the stems each one can deliver.
                </p>
              </>
            )}
          </aside>
        </div>
        </section>
        ) : null}

        {job?.status !== "completed" ? <JobProgress
          busy={busy}
          connectionIssue={connectionIssue}
          error={jobError || job?.error || ""}
          job={job}
          onCancel={cancel}
          onRetry={() => job?.job_id && refreshJob(job.job_id)}
          stage={stage}
        /> : null}
        <ResultsPanel job={job} />
        {job?.status !== "completed" && !job && !busy ? <LandingStory /> : null}
      </main>

      <footer>
        <span>STEM/SPLITTER</span>
        <p>Built for working musicians and honest listening.</p>
        <a href="#top">Back to top</a>
      </footer>
    </div>
  );
}

export default App;
