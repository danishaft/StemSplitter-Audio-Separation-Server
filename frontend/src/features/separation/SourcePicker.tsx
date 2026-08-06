import type { FormEvent } from "react";

import { formatDuration, importReason } from "./format";
import { Icon } from "./Icon";
import type { AudiusTrack } from "./types";

interface SourcePickerProps {
  audiusQuery: string;
  audiusTracks: AudiusTrack[];
  dragging: boolean;
  file: File | null;
  inputMode: "upload" | "audius";
  notice: string;
  searchingAudius: boolean;
  selectedTrack: AudiusTrack | null;
  onAcceptFile: (file: File | undefined) => void;
  onAudiusQueryChange: (query: string) => void;
  onDraggingChange: (dragging: boolean) => void;
  onInputModeChange: (mode: "upload" | "audius") => void;
  onSearchAudius: () => void;
  onSelectTrack: (track: AudiusTrack) => void;
}

export function SourcePicker({
  audiusQuery,
  audiusTracks,
  dragging,
  file,
  inputMode,
  onAcceptFile,
  onAudiusQueryChange,
  onDraggingChange,
  onInputModeChange,
  onSearchAudius,
  onSelectTrack,
  notice,
  searchingAudius,
  selectedTrack
}: SourcePickerProps) {
  function submitSearch(event: FormEvent): void {
    event.preventDefault();
    onSearchAudius();
  }

  function moveTab(nextMode: "upload" | "audius"): void {
    onInputModeChange(nextMode);
    window.requestAnimationFrame(() => {
      document.getElementById(`${nextMode}-tab`)?.focus();
    });
  }

  return (
    <section className="source-picker" aria-labelledby="source-title">
      <div className="section-heading">
        <span>01</span>
        <div>
          <p className="eyebrow">Source</p>
          <h2 id="source-title">Bring the record in</h2>
        </div>
      </div>

      <div className="source-tabs" role="tablist" aria-label="Audio source">
        <button
          aria-controls="upload-panel"
          aria-selected={inputMode === "upload"}
          className={inputMode === "upload" ? "active" : ""}
          id="upload-tab"
          onKeyDown={(event) => {
            if (["ArrowLeft", "ArrowRight"].includes(event.key)) {
              event.preventDefault();
              moveTab("audius");
            }
          }}
          onClick={() => onInputModeChange("upload")}
          role="tab"
          tabIndex={inputMode === "upload" ? 0 : -1}
          type="button"
        >
          Upload a file
        </button>
        <button
          aria-controls="audius-panel"
          aria-selected={inputMode === "audius"}
          className={inputMode === "audius" ? "active" : ""}
          id="audius-tab"
          onKeyDown={(event) => {
            if (["ArrowLeft", "ArrowRight"].includes(event.key)) {
              event.preventDefault();
              moveTab("upload");
            }
          }}
          onClick={() => onInputModeChange("audius")}
          role="tab"
          tabIndex={inputMode === "audius" ? 0 : -1}
          type="button"
        >
          Search Audius
        </button>
      </div>

      {inputMode === "upload" ? (
        <div aria-labelledby="upload-tab" id="upload-panel" role="tabpanel">
          <label
            className={`dropzone ${dragging ? "dropzone--active" : ""} ${file ? "dropzone--ready" : ""}`}
            onDragEnter={(event) => {
              event.preventDefault();
              onDraggingChange(true);
            }}
            onDragLeave={() => onDraggingChange(false)}
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => {
              event.preventDefault();
              onDraggingChange(false);
              onAcceptFile(event.dataTransfer.files[0]);
            }}
          >
            <input
              accept=".flac,.m4a,.mp3,.ogg,.wav"
              onChange={(event) => onAcceptFile(event.target.files?.[0])}
              type="file"
            />
            <span className="dropzone__icon"><Icon name={file ? "file" : "upload"} size={25} /></span>
            <span className="dropzone__copy">
              <strong>{file?.name || "Drop your mix here"}</strong>
              <small>
                {file
                  ? `${(file.size / 1024 / 1024).toFixed(1)} MB ready to upload`
                  : "WAV, FLAC, MP3, M4A, or OGG up to 500 MB"}
              </small>
            </span>
            <b>{file ? "Replace file" : "Choose file"}</b>
          </label>
        </div>
      ) : (
        <div aria-labelledby="audius-tab" className="audius-picker" id="audius-panel" role="tabpanel">
          <form className="catalog-search" onSubmit={submitSearch}>
            <label htmlFor="audius-query">Artist, song, or genre</label>
            <div>
              <span><Icon name="search" size={19} /></span>
              <input
                id="audius-query"
                maxLength={100}
                onChange={(event) => onAudiusQueryChange(event.target.value)}
                placeholder="Search derivative-friendly releases"
                value={audiusQuery}
              />
              <button disabled={searchingAudius} type="submit">
                {searchingAudius ? "Searching" : "Search"}
              </button>
            </div>
          </form>

          {audiusTracks.length ? (
            <div className="catalog-results" aria-label="Audius search results">
              {audiusTracks.map((track) => {
                const selected = selectedTrack?.id === track.id;
                return (
                  <article className={`catalog-track ${selected ? "catalog-track--selected" : ""}`} key={track.id}>
                    {track.artwork_url ? (
                      <img alt="" loading="lazy" src={track.artwork_url} />
                    ) : (
                      <div className="artwork-placeholder" aria-hidden="true"><Icon name="wave" /></div>
                    )}
                    <div className="track-copy">
                      <strong>{track.title}</strong>
                      <small>{track.artist} · {formatDuration(track.duration_seconds)}</small>
                      <span>{track.license || "License unavailable"}</span>
                    </div>
                    <button disabled={!track.can_import} onClick={() => onSelectTrack(track)} type="button">
                      {track.can_import
                        ? selected ? "Selected" : "Select"
                        : importReason(track.import_reason)}
                    </button>
                  </article>
                );
              })}
            </div>
          ) : (
            <div className="catalog-empty">
              <Icon name="search" size={23} />
              <p>Eligible tracks appear here with license and duration checked before import.</p>
            </div>
          )}
        </div>
      )}
      {notice ? <div className="source-notice" role="alert">{notice}</div> : null}
    </section>
  );
}
