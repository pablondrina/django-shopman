/** Prefix a path with the app's baseURL (handles the "/" no-op and trailing slash). */
export function apiPath(path: string, baseURL = "/"): string {
  const base = baseURL === "/" ? "" : baseURL.replace(/\/$/, "");
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return `${base}${normalized}`;
}
