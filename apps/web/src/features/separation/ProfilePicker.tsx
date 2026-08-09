import type { Capabilities } from "./types";

interface ProfilePickerProps {
  availability: "loading" | "ready" | "error";
  capabilities: Capabilities | null;
  disabled: boolean;
  profile: string;
  onChange: (profile: string) => void;
}

function profileDescription(name: string, tier: string, engine: unknown): string {
  if (name.includes("mvsep")) return "Adds optional specialist stems when remote analysis is available.";
  if (typeof engine === "string" && engine.includes("gpu")) {
    return "Highest-detail split for final listening and export.";
  }
  if (name.includes("quality")) return "Detailed local split for editing and export.";
  if (name.includes("preview")) return "Quick broad-stem check before a full split.";
  return tier ? `${tier} balance of speed and detail.` : "A balanced split for this session.";
}

export function ProfilePicker({
  availability,
  capabilities,
  disabled,
  onChange,
  profile
}: ProfilePickerProps) {
  const profiles = Object.entries(capabilities?.profiles || {}).filter(
    ([, metadata]) => metadata.public === true
  );

  return (
    <fieldset className="profile-picker" disabled={disabled || !profiles.length}>
      <legend>Choose a separation profile</legend>
      <p>Choose speed or detail for this session. Each option states what it can deliver.</p>
      {availability === "loading" ? (
        <div className="profile-loading" aria-live="polite">
          <span />
          <div>
            <strong>Checking available profiles</strong>
            <small>Separation starts as soon as the studio reconnects.</small>
          </div>
        </div>
      ) : null}
      {availability === "error" ? (
        <div className="profile-unavailable" role="status">
          <strong>Profiles are unavailable</strong>
          <small>Retry the studio connection above to continue.</small>
        </div>
      ) : null}
      <div className="profile-options">
        {profiles.map(([name, metadata]) => {
          const selected = name === profile;
          return (
            <label className={`profile-option ${selected ? "profile-option--selected" : ""}`} key={name}>
              <input
                checked={selected}
                name="separation-profile"
                onChange={() => onChange(name)}
                type="radio"
                value={name}
              />
              <span className="profile-option__radio" aria-hidden="true" />
              <span className="profile-option__copy">
                <strong>{metadata.label}</strong>
                <small>{profileDescription(name, metadata.tier, metadata.engine)}</small>
              </span>
              {name === capabilities?.recommended_profile ? <b>Recommended</b> : null}
              {name.includes("experimental") ? <b className="profile-option__flag">Experimental</b> : null}
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}
