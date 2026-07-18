// Transporte na layer operator-kit (server/utils/djangoProxy.ts, auto-importado).
export default defineEventHandler((event) => {
  const rawPath = event.context.params?.path || "";
  const path = Array.isArray(rawPath) ? rawPath.join("/") : rawPath;
  return proxyDjangoApi(event, path);
});
