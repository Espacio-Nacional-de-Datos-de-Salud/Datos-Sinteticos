import { type NextRequest } from "next/server";

const API_PROXY_TARGET = process.env.API_PROXY_TARGET ?? "http://localhost:8000";

const BACKEND_COLLECTION_ENDPOINTS = new Set([
  "business-rules-configurations",
  "configs",
  "evaluations",
  "files",
  "inspections",
  "models",
  "pipelines",
  "rule-presets",
  "simulations",
]);

const HOP_BY_HOP_HEADERS = new Set([
  "connection",
  "content-encoding",
  "content-length",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
]);

type RouteContext = {
  params: Promise<{ path?: string[] }>;
};

async function proxy(req: NextRequest, context: RouteContext): Promise<Response> {
  const { path = [] } = await context.params;
  const target = new URL(path.join("/"), `${API_PROXY_TARGET}/`);
  if (path.length === 1 && BACKEND_COLLECTION_ENDPOINTS.has(path[0])) {
    target.pathname = `/${path[0]}/`;
  }
  target.search = req.nextUrl.search;

  const headers = new Headers(req.headers);
  for (const header of HOP_BY_HOP_HEADERS) headers.delete(header);
  headers.set("host", target.host);

  const init: RequestInit & { duplex?: "half" } = {
    method: req.method,
    headers,
    redirect: "follow",
  };

  if (!["GET", "HEAD"].includes(req.method)) {
    init.body = req.body;
    init.duplex = "half";
  }

  const upstream = await fetch(target, init);
  const responseHeaders = new Headers(upstream.headers);
  for (const header of HOP_BY_HOP_HEADERS) responseHeaders.delete(header);

  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeaders,
  });
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
export const HEAD = proxy;
export const OPTIONS = proxy;
