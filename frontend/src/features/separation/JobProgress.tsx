import type { JobPayload } from "./types";

interface JobProgressProps {
  busy: boolean;
  error: string;
  job: JobPayload | null;
  onCancel: () => void;
  stage: string;
}

export function JobProgress({ busy, error, job, onCancel, stage }: JobProgressProps) {
  if (!job && !busy && !error) return null;
  const elapsed =
    job?.timings?.local_total_seconds ??
    job?.timings?.local_elapsed_seconds ??
    job?.timings?.worker_total_seconds;

  return (
    <section className="progress-panel" aria-live="polite">
      <div>
        <small>Job {job?.job_id?.slice(0, 8) || "preparing"}</small>
        <strong>{error || stage}</strong>
      </div>
      <div className="progress-actions">
        {elapsed != null ? <small>{Number(elapsed).toFixed(1)}s elapsed</small> : null}
        {busy && job?.job_id ? (
          <button className="text-button" onClick={onCancel}>Cancel</button>
        ) : null}
      </div>
      <div className={`progress-track ${busy ? "progress-track--active" : ""}`} />
      {job?.missing_features?.length ? (
        <p className="job-notice">Not available in this run: {job.missing_features.join(", ")}</p>
      ) : null}
      {job?.remote_adapter_status && job.remote_adapter_status !== "not_requested" ? (
        <p className="job-notice">
          Remote specialist lane: {job.remote_adapter_status}
          {job.remote_adapter_reason ? ` (${job.remote_adapter_reason})` : ""}
        </p>
      ) : null}
    </section>
  );
}
