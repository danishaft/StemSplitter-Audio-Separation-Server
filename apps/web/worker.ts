interface CloudflareBindings {
  API_ORIGIN: string;
  ASSETS: Fetcher;
  ORIGIN_VERIFY_SECRET: string;
}

function securityPolicy(nonce: string): string {
  return [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' https://clerk.com https://*.clerk.com https://*.clerk.accounts.dev`,
    "style-src 'self' 'unsafe-inline'",
    "connect-src 'self' https: wss:",
    "img-src 'self' data: https:",
    "media-src 'self' blob: https:",
    "font-src 'self'",
    "worker-src 'self' blob:",
    "frame-src 'self' https://challenges.cloudflare.com https://*.protect.clerk.com",
    "frame-ancestors 'none'",
    "form-action 'self'",
    "base-uri 'self'"
  ].join("; ");
}

function secureResponse(response: Response, nonce?: string): Response {
  const headers = new Headers(response.headers);
  if (nonce) headers.set("Content-Security-Policy", securityPolicy(nonce));
  headers.set(
    "Permissions-Policy",
    "camera=(), microphone=(), geolocation=(), payment=()"
  );
  headers.set("Referrer-Policy", "strict-origin-when-cross-origin");
  headers.set("X-Content-Type-Options", "nosniff");
  headers.set("X-Frame-Options", "DENY");
  return new Response(response.body, {
    headers,
    status: response.status,
    statusText: response.statusText
  });
}

function createNonce(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return btoa(String.fromCharCode(...bytes));
}

async function forwardApi(
  request: Request,
  env: CloudflareBindings
): Promise<Response> {
  const incoming = new URL(request.url);
  const upstream = new URL(env.API_ORIGIN);
  const upstreamBasePath = upstream.pathname.replace(/\/$/, "");
  const forwardedPath = incoming.pathname.slice("/api".length) || "/";
  upstream.pathname = `${upstreamBasePath}${forwardedPath}`;
  upstream.search = incoming.search;

  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.delete("x-stemsplitter-origin-verify");
  headers.set("X-StemSplitter-Origin-Verify", env.ORIGIN_VERIFY_SECRET);
  headers.set("X-Forwarded-Host", incoming.host);
  headers.set("X-Forwarded-Proto", "https");

  const hasBody = request.method !== "GET" && request.method !== "HEAD";
  const response = await fetch(upstream, {
    body: hasBody ? request.body : undefined,
    headers,
    method: request.method,
    redirect: "manual"
  });
  const secured = secureResponse(response);
  secured.headers.set("Cache-Control", "no-store");
  return secured;
}

async function serveAsset(request: Request, env: CloudflareBindings) {
  const response = await env.ASSETS.fetch(request);
  if (!response.headers.get("content-type")?.startsWith("text/html")) {
    return secureResponse(response);
  }

  const nonce = createNonce();
  const transformed = new HTMLRewriter()
    .on("script", {
      element(element) {
        element.setAttribute("nonce", nonce);
      }
    })
    .transform(response);
  return secureResponse(transformed, nonce);
}

export default {
  fetch(request, env) {
    const pathname = new URL(request.url).pathname;
    if (pathname === "/api" || pathname.startsWith("/api/")) {
      return forwardApi(request, env);
    }
    return serveAsset(request, env);
  }
} satisfies ExportedHandler<CloudflareBindings>;
