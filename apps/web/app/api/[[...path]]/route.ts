import { getCloudflareContext } from "@opennextjs/cloudflare";
import type { NextRequest } from "next/server";

export const dynamic = "force-dynamic";

interface CloudflareBindings {
  API_ORIGIN: string;
  ORIGIN_VERIFY_SECRET: string;
}

async function forward(request: NextRequest): Promise<Response> {
  const { env } = await getCloudflareContext({ async: true });
  const bindings = env as unknown as CloudflareBindings;
  const incoming = new URL(request.url);
  const upstreamUrl = new URL(bindings.API_ORIGIN);
  upstreamUrl.pathname = incoming.pathname.slice("/api".length) || "/";
  upstreamUrl.search = incoming.search;

  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.delete("x-stemsplitter-origin-verify");
  headers.set("X-StemSplitter-Origin-Verify", bindings.ORIGIN_VERIFY_SECRET);
  headers.set("X-Forwarded-Host", incoming.host);
  headers.set("X-Forwarded-Proto", "https");

  const hasBody = request.method !== "GET" && request.method !== "HEAD";
  const upstream = await fetch(upstreamUrl, {
    body: hasBody ? request.body : undefined,
    headers,
    method: request.method,
    redirect: "manual"
  });
  const responseHeaders = new Headers(upstream.headers);
  responseHeaders.set("Cache-Control", "no-store");
  return new Response(upstream.body, {
    headers: responseHeaders,
    status: upstream.status,
    statusText: upstream.statusText
  });
}

export const DELETE = forward;
export const GET = forward;
export const HEAD = forward;
export const OPTIONS = forward;
export const PATCH = forward;
export const POST = forward;
export const PUT = forward;
