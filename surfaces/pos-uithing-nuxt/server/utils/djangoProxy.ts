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

export async function proxyDjangoApi(event: H3Event, path: string) {
  return proxyDjangoPath(event, `/api/v1/${path}`);
}

export async function proxyDjangoPath(event: H3Event, fullPath: string) {
  const config = useRuntimeConfig(event);
  const method = event.method || "GET";
  const normalizedPath = fullPath.endsWith("/") ? fullPath : `${fullPath}/`;
  const target = withQuery(`${config.djangoBaseUrl}${normalizedPath}`, getQuery(event));

  const headers: Record<string, string> = {
    accept: getRequestHeader(event, "accept") || "application/json",
  };

  const cookie = getRequestHeader(event, "cookie");
  if (cookie) headers.cookie = cookie;

  const contentType = getRequestHeader(event, "content-type");
  if (contentType) headers["content-type"] = contentType;

  const origin = getRequestHeader(event, "origin");
  if (origin) headers.origin = origin;

  const referer = getRequestHeader(event, "referer");
  if (referer) headers.referer = referer;

  const csrfCookie = cookie
    ?.split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith("csrftoken="))
    ?.slice("csrftoken=".length);
  if (csrfCookie) headers["x-csrftoken"] = decodeURIComponent(csrfCookie);

  const body = ["GET", "HEAD"].includes(method) ? undefined : await readRawBody(event, false);

  const response = await $fetch.raw(target, {
    method,
    headers,
    body,
    ignoreResponseError: true,
    redirect: "manual",
  });

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
