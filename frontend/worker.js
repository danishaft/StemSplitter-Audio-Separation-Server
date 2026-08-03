const API_PREFIX = "/api";

function withSecurityHeaders(response, cacheControl) {
  const headers = new Headers(response.headers);
  headers.set("Cache-Control", cacheControl);
  headers.set("Referrer-Policy", "strict-origin-when-cross-origin");
  headers.set("X-Content-Type-Options", "nosniff");
  headers.set("X-Frame-Options", "DENY");
  headers.set(
    "Permissions-Policy",
    "camera=(), microphone=(), geolocation=(), payment=()"
  );
  headers.set(
    "Content-Security-Policy",
    "default-src 'self'; connect-src 'self' https:; img-src 'self' data:; " +
      "media-src 'self' blob: https:; style-src 'self' 'unsafe-inline'; " +
      "font-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'self'"
  );
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers
  });
}

export default {
  async fetch(request, env) {
    const incoming = new URL(request.url);
    if (
      incoming.pathname === API_PREFIX ||
      incoming.pathname.startsWith(`${API_PREFIX}/`)
    ) {
      const origin = new URL(env.API_ORIGIN);
      origin.pathname = incoming.pathname.slice(API_PREFIX.length) || "/";
      origin.search = incoming.search;

      const headers = new Headers(request.headers);
      headers.delete("x-stemsplitter-origin-verify");
      headers.set("X-StemSplitter-Origin-Verify", env.ORIGIN_VERIFY_SECRET);
      headers.set("X-Forwarded-Host", incoming.host);
      headers.set("X-Forwarded-Proto", "https");

      const upstream = await fetch(
        new Request(origin, {
          method: request.method,
          headers,
          body: request.body,
          redirect: "manual"
        })
      );
      return withSecurityHeaders(upstream, "no-store");
    }

    const asset = await env.ASSETS.fetch(request);
    const cacheControl = incoming.pathname.startsWith("/assets/")
      ? "public, max-age=31536000, immutable"
      : "no-cache";
    return withSecurityHeaders(asset, cacheControl);
  }
};
