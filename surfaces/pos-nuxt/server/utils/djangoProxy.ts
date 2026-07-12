import {
  appendResponseHeader,
  getQuery,
  getRequestHeader,
  readRawBody,
  setResponseStatus,
  splitCookiesString,
  type H3Event,
} from "h3";
import { withQuery } from "ufo";

const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export function csrfTokenFromCookieHeader(cookie: string | undefined): string {
  return cookie
    ?.split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith("csrftoken="))
    ?.slice("csrftoken=".length) || "";
}

export function mergeSetCookieIntoCookieHeader(cookie: string | undefined, setCookie: string): string {
  const [pair] = setCookie.split(";");
  const [name, ...valueParts] = (pair ?? "").split("=");
  const value = valueParts.join("=");
  if (!name || value == null) return cookie || "";

  const next = new Map<string, string>();
  for (const part of (cookie || "").split(";")) {
    const [cookieName, ...cookieValue] = part.trim().split("=");
    if (cookieName) next.set(cookieName, cookieValue.join("="));
  }
  next.set(name, value);
  return Array.from(next.entries()).map(([cookieName, cookieValue]) => `${cookieName}=${cookieValue}`).join("; ");
}

async function ensureDjangoCsrfCookie(
  event: H3Event,
  djangoBaseUrl: string,
  cookie: string | undefined,
): Promise<{ cookie: string | undefined; token: string }> {
  let token = csrfTokenFromCookieHeader(cookie);
  if (token) return { cookie, token: decodeURIComponent(token) };

  const response = await $fetch.raw(`${djangoBaseUrl}/admin/login/`, {
    method: "GET",
    headers: {
      accept: "text/html",
      ...(cookie ? { cookie } : {}),
    },
    ignoreResponseError: true,
  });

  let mergedCookie = cookie;
  const setCookie = response.headers.get("set-cookie");
  if (setCookie) {
    for (const cookieHeader of splitCookiesString(setCookie)) {
      appendResponseHeader(event, "set-cookie", cookieHeader);
      mergedCookie = mergeSetCookieIntoCookieHeader(mergedCookie, cookieHeader);
    }
  }

  token = csrfTokenFromCookieHeader(mergedCookie);
  return { cookie: mergedCookie, token: token ? decodeURIComponent(token) : "" };
}

export async function proxyDjangoApi(event: H3Event, path: string) {
  return proxyDjangoPath(event, `/api/v1/${path}`);
}

export async function proxyDjangoPath(event: H3Event, fullPath: string) {
  const config = useRuntimeConfig(event);
  const method = event.method || "GET";
  const isUnsafeMethod = UNSAFE_METHODS.has(method.toUpperCase());
  const normalizedPath = fullPath.endsWith("/") ? fullPath : `${fullPath}/`;
  const target = withQuery(`${config.djangoBaseUrl}${normalizedPath}`, getQuery(event));
  const djangoOrigin = new URL(config.djangoBaseUrl).origin;

  const headers: Record<string, string> = {
    accept: getRequestHeader(event, "accept") || "application/json",
  };

  let cookie = getRequestHeader(event, "cookie");
  if (cookie) headers.cookie = cookie;

  const contentType = getRequestHeader(event, "content-type");
  if (contentType) headers["content-type"] = contentType;

  if (isUnsafeMethod) {
    headers.origin = djangoOrigin;
    headers.referer = `${djangoOrigin}/`;
  }

  const clientCsrfHeader = getRequestHeader(event, "x-csrftoken") || getRequestHeader(event, "x-csrf-token");
  const csrfCookie = csrfTokenFromCookieHeader(cookie);
  if (csrfCookie) headers["x-csrftoken"] = decodeURIComponent(csrfCookie);
  else if (clientCsrfHeader) headers["x-csrftoken"] = clientCsrfHeader;

  if (isUnsafeMethod && !headers["x-csrftoken"]) {
    const csrf = await ensureDjangoCsrfCookie(event, config.djangoBaseUrl, cookie);
    cookie = csrf.cookie;
    if (cookie) headers.cookie = cookie;
    if (csrf.token) headers["x-csrftoken"] = csrf.token;
  }

  const body = ["GET", "HEAD"].includes(method) ? undefined : await readRawBody(event, false);

  const response = await $fetch.raw(target, {
    method,
    headers,
    body,
    ignoreResponseError: true,
    redirect: "manual",
  });

  // Sanidade de contrato: o Django carimba /api/v1/ com X-API-Version; major
  // divergente vira warning estruturado no Nitro (operator-kit/server/utils/
  // apiVersion.ts, auto-importado) — nunca bloqueia a resposta.
  warnOnApiVersionMismatch(response.headers.get("x-api-version"), { path: normalizedPath });

  const setCookie = response.headers.get("set-cookie");
  if (setCookie) {
    for (const cookieHeader of splitCookiesString(setCookie)) {
      appendResponseHeader(event, "set-cookie", cookieHeader);
    }
  }

  const location = response.headers.get("location");
  if (location) appendResponseHeader(event, "location", location);

  const responseContentType = response.headers.get("content-type");
  if (responseContentType) appendResponseHeader(event, "content-type", responseContentType);

  setResponseStatus(event, response.status);
  return response._data;
}
