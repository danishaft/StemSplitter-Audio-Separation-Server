import {
  api,
  apiError,
  apiPath,
  authHeaders,
  type GetAccessToken
} from "@stemsplitter/api-client";

import type { AudiusTrack, JobPayload } from "./types";

async function json<T>(response: Response): Promise<T> {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.message || payload.error || `Request failed (${response.status})`);
  }
  return payload as T;
}

async function submitMultipart(
  file: File,
  profile: string,
  idempotencyKey: string,
  getToken: GetAccessToken
): Promise<JobPayload> {
  const body = new FormData();
  body.append("file", file);
  body.append("profile", profile);
  return json<JobPayload>(
    await fetch(apiPath("/jobs"), {
      method: "POST",
      headers: { ...await authHeaders(getToken), "Idempotency-Key": idempotencyKey },
      body
    })
  );
}

export async function submitUploadJob(
  file: File,
  profile: string,
  idempotencyKey: string,
  setStage: (stage: string) => void,
  getToken: GetAccessToken
): Promise<JobPayload> {
  setStage("Requesting private upload");
  const {
    data: grant,
    error: grantError,
    response: grantResponse
  } = await api.POST("/uploads", {
    headers: await authHeaders(getToken),
    body: {
      filename: file.name,
      content_type: file.type || "application/octet-stream"
    }
  });

  if (grantError || !grant) {
    const errorPayload = grantError as { error?: string };
    if (grantResponse.status === 503 && errorPayload?.error === "direct_upload_unavailable") {
      setStage("Uploading through local development path");
      return submitMultipart(file, profile, idempotencyKey, getToken);
    }
    throw apiError(grantError, grantResponse);
  }
  if (grant.max_bytes && file.size > grant.max_bytes) {
    throw new Error(`File exceeds the ${Math.round(grant.max_bytes / 1024 / 1024)} MB limit`);
  }

  setStage("Uploading directly to private storage");
  const upload = await fetch(grant.url, {
    method: grant.method || "PUT",
    headers: grant.headers || { "Content-Type": file.type || "application/octet-stream" },
    body: file
  });
  if (!upload.ok) throw new Error(`Storage upload failed (${upload.status})`);

  setStage("Queueing separation job");
  const { data, error, response } = await api.POST("/jobs", {
    headers: {
      ...await authHeaders(getToken),
      "Idempotency-Key": idempotencyKey
    },
    body: {
      profile,
      input: {
        filename: grant.filename || file.name,
        object: grant.object
      }
    }
  });
  if (error || !data) throw apiError(error, response);
  return data;
}

export async function submitAudiusJob(
  trackId: string,
  profile: string,
  idempotencyKey: string,
  setStage: (stage: string) => void,
  getToken: GetAccessToken
): Promise<JobPayload> {
  setStage("Validating licence and importing from Audius");
  const { data, error, response } = await api.POST("/jobs", {
    headers: {
      ...await authHeaders(getToken),
      "Idempotency-Key": idempotencyKey
    },
    body: {
      profile,
      source: {
        provider: "audius",
        track_id: trackId
      }
    }
  });
  if (error || !data) throw apiError(error, response);
  return data;
}

export async function searchAudiusTracks(query: string): Promise<AudiusTrack[]> {
  const { data, error, response } = await api.GET("/sources/audius/search", {
    params: { query: { q: query, limit: "12" } }
  });
  if (error || !data) throw apiError(error, response);
  return data.tracks;
}
