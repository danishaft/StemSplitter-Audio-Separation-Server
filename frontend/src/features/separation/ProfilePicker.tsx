import type { Capabilities } from "./types";

interface ProfilePickerProps {
  capabilities: Capabilities | null;
  disabled: boolean;
  profile: string;
  onChange: (profile: string) => void;
}

function profileDescription(name: string, tier: string, engine: unknown): string {
  if (name.includes("mvsep")) return "Adds an optional remote specialist pass.";
  if (typeof engine === "string" && engine.includes("gpu")) {
    return "GPU evaluation path with full artifact packaging.";
  }
  if (name.includes("quality")) return "Local quality path with full artifact packaging.";
  if (name.includes("preview")) return "Fast local broad-stem preview.";
  return tier ? `${tier} separation profile.` : "Available separation profile.";
}

export function ProfilePicker({
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
      <p>Quality claims apply to the selected profile, not every model in the registry.</p>
      {!capabilities ? (
        <div className="profile-loading" aria-live="polite">
          <span />
          <div>
            <strong>Checking available profiles</strong>
            <small>The start control stays locked until the server contract is ready.</small>
          </div>
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
