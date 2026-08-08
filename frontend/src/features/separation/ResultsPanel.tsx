import { useAuth } from "@clerk/react";
import { useEffect, useState } from "react";

import { apiPath, authHeaders } from "../../api/client";
import { formatDuration } from "./format";
import { Icon } from "./Icon";
import type { JobPayload } from "./types";
import { useStemTransport } from "./useStemTransport";
import { WaveformCanvas } from "./WaveformCanvas";

const STEM_ORDER = [
  "vocals",
  "drums",
  "bass",
  "piano",
  "guitar",
  "electric_guitar",
  "acoustic_guitar",
  "synth",
  "strings",
  "other"
];

const STEM_COLORS: Record<string, string> = {
  vocals: "#ff6f91",
  lead_vocals: "#ff6f91",
  backing_vocals: "#ff91aa",
  drums: "#ffb84d",
  kick: "#ffb84d",
  snare: "#ffd07b",
  bass: "#42d3e8",
  piano: "#73a2ff",
  keys: "#73a2ff",
  guitar: "#61d9a6",
  electric_guitar: "#61d9a6",
  acoustic_guitar: "#83e2bb",
  synth: "#f08bc3",
  strings: "#55d6c2",
  other: "#9ba8ba",
  instrumental: "#cbd5e1"
};

const ADDITIONAL_GROUPS = [
  ["broad_stems", "Broad stems"],
  ["derived_stems", "Derived candidates"],
  ["specialist_substems", "Specialist candidates"],
  ["tempo_locked_wavs", "Tempo-locked WAVs"],
  ["midi", "MIDI guides"],
  ["analysis", "Analysis"],
] as const;

interface WaveformStem {
  duration_seconds: number;
  peak_amplitude: number;
  peaks: number[];
  sample_rate: number;
}

interface WaveformAnalysis {
  bins: number;
  duration_seconds: number;
  normalization: string;
  stems: Record<string, WaveformStem>;
  version: number;
}

interface ArtifactMetadata {
  artifact_group?: string;
  publish_reason?: string;
  publish_status?: string;
  quality_score?: number;
  source_model?: string;
  warnings?: string[];
}

interface ResultsPanelProps {
  job: JobPayload | null;
}

function labelFor(name: string): string {
  return name.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function combinePeaks(stems: WaveformStem[]): number[] | undefined {
  const length = Math.max(...stems.map((stem) => stem.peaks.length), 0);
  if (!length) return undefined;
  return Array.from({ length }, (_, index) =>
    Math.max(...stems.map((stem) => stem.peaks[index] || 0))
  );
}

function sortStems([left]: [string, string], [right]: [string, string]): number {
  const leftIndex = STEM_ORDER.indexOf(left);
  const rightIndex = STEM_ORDER.indexOf(right);
  return (leftIndex < 0 ? 999 : leftIndex) - (rightIndex < 0 ? 999 : rightIndex)
    || left.localeCompare(right);
}

export function ResultsPanel({ job }: ResultsPanelProps) {
  const { getToken } = useAuth();
  const [analysis, setAnalysis] = useState<WaveformAnalysis | null>(null);
  const [analysisError, setAnalysisError] = useState("");
  const [muted, setMuted] = useState<Set<string>>(new Set());
  const [soloed, setSoloed] = useState<Set<string>>(new Set());
  const [selectedStem, setSelectedStem] = useState("");
  const [mobileInspectorOpen, setMobileInspectorOpen] = useState(false);
  const [volumes, setVolumes] = useState<Record<string, number>>({});
  const mainArtifacts = job?.artifacts?.main_stems || {};
  const fallbackArtifacts = job?.artifacts?.broad_stems || {};
  const artifacts = Object.keys(mainArtifacts).length ? mainArtifacts : fallbackArtifacts;
  const stems = Object.entries(artifacts).sort(sortStems);
  const waveformUrl = job?.artifacts?.analysis?.waveform_peaks;
  const trackName = (job as JobPayload & { input_name?: string } | null)?.input_name
    ?.replace(/\.[^.]+$/, "") || "Stem session";
  const metadata = ((job as JobPayload & {
    artifact_metadata?: { main_stems?: Record<string, ArtifactMetadata> };
  } | null)?.artifact_metadata?.main_stems || {}) as Record<string, ArtifactMetadata>;

  useEffect(() => {
    if (!waveformUrl) {
      setAnalysis(null);
      setAnalysisError(stems.length ? "Waveform analysis was not published for this job." : "");
      return undefined;
    }
    const controller = new AbortController();
    setAnalysisError("");
    void authHeaders(getToken)
      .then((headers) => fetch(apiPath(waveformUrl), { headers, signal: controller.signal }))
      .then((response) => {
        if (!response.ok) throw new Error(`Waveform analysis failed (${response.status})`);
        return response.json() as Promise<WaveformAnalysis>;
      })
      .then(setAnalysis)
      .catch((requestError: unknown) => {
        if (requestError instanceof DOMException && requestError.name === "AbortError") return;
        setAnalysisError("Waveform analysis is unavailable. Audio downloads remain intact.");
      });
    return () => controller.abort();
  }, [getToken, waveformUrl]);

  useEffect(() => {
    if (!selectedStem && stems.length) setSelectedStem(stems[0][0]);
  }, [selectedStem, stems]);

  const transport = useStemTransport({
    duration: analysis?.duration_seconds || 0,
    muted,
    soloed,
    tracks: stems.map(([id, href]) => ({ id, src: apiPath(href) })),
    volumes
  });

  if (!job || (!stems.length && job.status !== "completed")) return null;

  const selectedHref = artifacts[selectedStem];
  const selectedMetadata = metadata[selectedStem] || {};
  const selectedScore = typeof selectedMetadata.quality_score === "number"
    ? selectedMetadata.quality_score
    : null;
  const masterPeaks = combinePeaks(Object.values(analysis?.stems || {}));
  const bundleHref = job.artifacts?.bundles?.stems;

  function toggleSet(
    setter: React.Dispatch<React.SetStateAction<Set<string>>>,
    stem: string
  ): void {
    setter((current) => {
      const next = new Set(current);
      if (next.has(stem)) next.delete(stem);
      else next.add(stem);
      return next;
    });
  }

  return (
    <section className="workspace" id="results" aria-labelledby="workspace-title">
      <header className="workspace__project-bar">
        <div>
          <p className="workspace__eyebrow">Completed session</p>
          <h2 id="workspace-title">{trackName}</h2>
          <span>
            {formatDuration(transport.duration)} · {stems.length} published stems · 44.1 kHz
          </span>
        </div>
        <div className="workspace__project-actions">
          <span className="profile-chip">QUALITY / {stems.length} STEM</span>
          {bundleHref ? (
            <a className="primary-action" download href={apiPath(bundleHref)}>
              Export session <Icon name="download" size={17} />
            </a>
          ) : null}
        </div>
      </header>

      {analysisError ? <p className="workspace__analysis-notice">{analysisError}</p> : null}

      <div className="workspace__mobile-master">
        <span>Master timeline</span>
        <WaveformCanvas
          color="#cbd5e1"
          currentTime={transport.currentTime}
          duration={transport.duration}
          label="master timeline"
          onSeek={transport.seek}
          peaks={masterPeaks}
        />
      </div>

      <div className="workspace__body">
        <div className="workspace__tracks" role="region" aria-label="Published stem mixer">
          <div className="timeline-ruler" aria-hidden="true">
            {[0, 0.25, 0.5, 0.75, 1].map((ratio) => (
              <span key={ratio}>{formatDuration(transport.duration * ratio)}</span>
            ))}
          </div>
          {stems.map(([name, href]) => {
            const color = STEM_COLORS[name] || "#9ba8ba";
            const score = metadata[name]?.quality_score;
            const isMuted = muted.has(name);
            const isSolo = soloed.has(name);
            return (
              <article
                className={`channel ${selectedStem === name ? "channel--selected" : ""}`}
                key={name}
                style={{ "--stem-color": color } as React.CSSProperties}
              >
                <button
                  className="channel__identity"
                  onClick={() => {
                    setSelectedStem(name);
                    setMobileInspectorOpen(true);
                  }}
                  type="button"
                >
                  <span className="channel__name">{labelFor(name)}</span>
                  <small>
                    {typeof score === "number" ? `READY · ${score.toFixed(2)}` : "PUBLISHED"}
                  </small>
                </button>
                <div className="channel__switches">
                  <button
                    aria-label={`${isMuted ? "Unmute" : "Mute"} ${labelFor(name)}`}
                    aria-pressed={isMuted}
                    onClick={() => toggleSet(setMuted, name)}
                    type="button"
                  >M</button>
                  <button
                    aria-label={`${isSolo ? "Unsolo" : "Solo"} ${labelFor(name)}`}
                    aria-pressed={isSolo}
                    onClick={() => toggleSet(setSoloed, name)}
                    type="button"
                  >S</button>
                </div>
                <WaveformCanvas
                  color={color}
                  currentTime={transport.currentTime}
                  duration={transport.duration}
                  label={labelFor(name)}
                  onSeek={transport.seek}
                  peaks={analysis?.stems?.[name]?.peaks}
                />
              </article>
            );
          })}
        </div>

        <aside className={`inspector ${mobileInspectorOpen ? "inspector--open" : ""}`}>
          <button
            aria-label="Close channel controls"
            className="inspector__close"
            onClick={() => setMobileInspectorOpen(false)}
            type="button"
          >×</button>
          <p className="workspace__eyebrow">Selected channel</p>
          <h3>{selectedStem ? labelFor(selectedStem) : "Select a stem"}</h3>
          <p className="inspector__description">Published audio ready for critical listening.</p>
          <div className="quality-badge">
            <span />
            {selectedScore == null ? "Published" : `Accepted · ${selectedScore.toFixed(2)}`}
          </div>

          <label className="mixer-control">
            <span>Volume <b>{Math.round((volumes[selectedStem] ?? 1) * 100)}%</b></span>
            <input
              max="1"
              min="0"
              onChange={(event) => setVolumes((current) => ({
                ...current,
                [selectedStem]: Number(event.target.value)
              }))}
              step="0.01"
              type="range"
              value={volumes[selectedStem] ?? 1}
            />
          </label>

          <div className="inspector__actions">
            <button
              aria-pressed={muted.has(selectedStem)}
              onClick={() => toggleSet(setMuted, selectedStem)}
              type="button"
            >Mute</button>
            <button
              aria-pressed={soloed.has(selectedStem)}
              onClick={() => toggleSet(setSoloed, selectedStem)}
              type="button"
            >Solo</button>
          </div>

          <div className="quality-note">
            <span>Quality note</span>
            <p>
              {selectedMetadata.warnings?.length
                ? selectedMetadata.warnings.map((warning) => warning.replaceAll("_", " ")).join(" · ")
                : selectedMetadata.publish_reason?.replaceAll("_", " ") || "No release warnings were reported."}
            </p>
          </div>

          {selectedHref ? (
            <a className="primary-action inspector__download" download href={apiPath(selectedHref)}>
              Download {selectedStem}.wav <Icon name="download" size={17} />
            </a>
          ) : null}
        </aside>
        {mobileInspectorOpen ? (
          <button
            aria-label="Close channel controls"
            className="inspector-scrim"
            onClick={() => setMobileInspectorOpen(false)}
            type="button"
          />
        ) : null}
      </div>

      <div className="master-transport" aria-label="Session transport">
        <button
          aria-label={transport.playing ? "Pause session" : "Play session"}
          className="master-transport__play"
          onClick={transport.toggle}
          type="button"
        >
          <Icon name={transport.playing ? "pause" : "play"} size={22} />
        </button>
        <div className="master-transport__time">
          <span>{formatDuration(transport.currentTime)} / {formatDuration(transport.duration)}</span>
          <input
            aria-label="Seek session"
            max={transport.duration || 1}
            min="0"
            onChange={(event) => transport.seek(Number(event.target.value))}
            step="0.1"
            type="range"
            value={Math.min(transport.currentTime, transport.duration || 1)}
          />
        </div>
        <div className="master-transport__meta">
          <span>SYNCED</span>
          <b>1.00x</b>
        </div>
      </div>
      {transport.error ? <p className="transport-error">{transport.error}</p> : null}

      <details className="additional-artifacts">
        <summary>Additional files and analysis</summary>
        <div>
          {ADDITIONAL_GROUPS.map(([key, label]) => {
            const group = job.artifacts?.[key];
            if (!group || !Object.keys(group).length) return null;
            return (
              <section key={key}>
                <h3>{label}</h3>
                {Object.entries(group).map(([name, href]) => (
                  <a download href={apiPath(href)} key={`${key}-${name}`}>
                    {labelFor(name)} <Icon name="download" size={15} />
                  </a>
                ))}
              </section>
            );
          })}
        </div>
      </details>
    </section>
  );
}
