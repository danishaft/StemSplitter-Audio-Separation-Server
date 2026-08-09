import { Icon } from "./Icon";
import type { JobPayload } from "./types";

interface JobProgressProps {
  busy: boolean;
  connectionIssue: boolean;
  error: string;
  job: JobPayload | null;
  onCancel: () => void;
  onRetry: () => void;
  stage: string;
}

const STEPS = ["Source ready", "Queued", "Separating", "Packaging"];

function activeStep(status: string, stage: string): number {
  const value = `${status} ${stage}`.toLowerCase();
  if (value.includes("complete") || value.includes("package")) return 3;
  if (value.includes("process") || value.includes("separat") || value.includes("worker")) return 2;
  if (value.includes("queue") || value.includes("prepar") || value.includes("upload")) return 1;
  return 0;
}

export function JobProgress({
  busy,
  connectionIssue,
  error,
  job,
  onCancel,
  onRetry,
  stage
}: JobProgressProps) {
  if (!job && !busy && !error) return null;

  const elapsed = job?.timings?.local_total_seconds
    ?? job?.timings?.local_elapsed_seconds
    ?? job?.timings?.worker_total_seconds;
  const currentStep = activeStep(job?.status || "", stage);
  const isFailure = Boolean(error) || ["error", "failed"].includes(job?.status || "");
  const isCancelled = job?.status === "cancelled";
  const title = isFailure
    ? "The session needs attention"
    : isCancelled
      ? "Separation cancelled"
      : job?.status === "completed"
        ? "Your stems are ready"
        : stage;

  return (
    <section
      aria-atomic="true"
      aria-live="polite"
      className={`job-panel ${isFailure ? "job-panel--error" : ""}`}
      id="job-status"
    >
      <div className="job-panel__heading">
        <div>
          <p className="eyebrow">Session {job?.job_id?.slice(0, 8) || "preparing"}</p>
          <h2>{title}</h2>
          {error ? <p className="job-panel__message">{error}</p> : null}
        </div>
        <div className="job-panel__actions">
          {elapsed != null ? <span>{Number(elapsed).toFixed(1)}s elapsed</span> : null}
          {connectionIssue && job?.job_id ? (
            <button className="button-secondary" onClick={onRetry} type="button">Retry status</button>
          ) : null}
          {busy && job?.job_id && !connectionIssue ? (
            <button className="button-quiet" onClick={onCancel} type="button">Cancel session</button>
          ) : null}
        </div>
      </div>

      {!isFailure && !isCancelled ? (
        <ol className="job-steps" aria-label="Separation progress">
          {STEPS.map((label, index) => {
            const complete = job?.status === "completed" || index < currentStep;
            const active = !complete && index === currentStep;
            return (
              <li className={complete ? "complete" : active ? "active" : ""} key={label}>
                <span>{complete ? <Icon name="check" size={15} /> : index + 1}</span>
                <strong>{label}</strong>
              </li>
            );
          })}
        </ol>
      ) : null}

      {busy && !connectionIssue ? (
        <div className="progress-track" role="progressbar" aria-label={stage}>
          <span />
        </div>
      ) : null}

      {job?.missing_features?.length ? (
        <div className="inline-notice">
          <strong>Not available in this run</strong>
          <p>{job.missing_features.map((feature) => feature.replaceAll("_", " ")).join(" · ")}</p>
        </div>
      ) : null}
      {job?.remote_adapter_status && job.remote_adapter_status !== "not_requested" ? (
        <div className="inline-notice">
          <strong>Optional specialist lane: {job.remote_adapter_status.replaceAll("_", " ")}</strong>
          {job.remote_adapter_reason ? <p>{job.remote_adapter_reason.replaceAll("_", " ")}</p> : null}
        </div>
      ) : null}
    </section>
  );
}
