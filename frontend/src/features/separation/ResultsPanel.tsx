import { ArtifactCard } from "./ArtifactCard";
import type { JobPayload } from "./types";

const ADDITIONAL_GROUPS = [
  ["broad_stems", "Broad stems"],
  ["derived_stems", "Derived candidates"],
  ["specialist_substems", "Specialist candidates"],
  ["tempo_locked_wavs", "Tempo-locked WAVs"],
  ["midi", "MIDI guides"],
  ["analysis", "Analysis"]
] as const;

interface ResultsPanelProps {
  job: JobPayload | null;
}

export function ResultsPanel({ job }: ResultsPanelProps) {
  const artifacts = job?.artifacts?.main_stems || {};
  return (
    <section className="results" id="results">
      <p className="eyebrow">02 / Results</p>
      <div className="results-heading">
        <h2>Listen before you download</h2>
        {job?.artifacts?.bundles?.stems ? (
          <a className="bundle-link" href={job.artifacts.bundles.stems}>Download bundle</a>
        ) : null}
      </div>
      {Object.keys(artifacts).length ? (
        <div className="stem-grid">
          {Object.entries(artifacts).map(([name, href]) => (
            <ArtifactCard
              key={name}
              name={name}
              href={href}
              parent={["vocals", "instrumental"].includes(name)}
            />
          ))}
        </div>
      ) : (
        <div className="empty-state">
          Completed stems will appear here with individual playback and downloads.
        </div>
      )}
      {ADDITIONAL_GROUPS.map(([key, label]) => {
        const group = job?.artifacts?.[key];
        if (!group || !Object.keys(group).length) return null;
        return (
          <section className="artifact-group" key={key}>
            <small className="artifact-group__label">{label}</small>
            <div className="stem-grid">
              {Object.entries(group).map(([name, href]) => (
                <ArtifactCard key={`${key}-${name}`} name={name} href={href} />
              ))}
            </div>
          </section>
        );
      })}
    </section>
  );
}
