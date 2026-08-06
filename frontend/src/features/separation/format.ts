export function formatDuration(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = Math.round(totalSeconds % 60);
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

export function importReason(reason: string): string {
  const labels: Record<string, string> = {
    all_rights_reserved: "All rights reserved",
    commercial_use_not_allowed: "Noncommercial licence",
    derivatives_not_allowed: "Derivatives prohibited",
    download_not_enabled: "Download disabled",
    download_requires_access: "Gated download",
    duration_limit_exceeded: "Track exceeds duration limit",
    duration_missing: "Duration unavailable",
    license_missing: "License unavailable",
    license_not_supported: "Unsupported license"
  };
  return labels[reason] || reason.replaceAll("_", " ");
}
