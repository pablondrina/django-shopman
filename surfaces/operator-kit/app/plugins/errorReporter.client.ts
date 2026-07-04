// Captura erros não-tratados do cliente de operador e os reporta ao Django
// (`reportClientError`). Inerte em dev (só loga no console) para não poluir a
// observabilidade com ruído de desenvolvimento. Dedupe + cap para não virar dreno.
import { reportClientError } from "../utils/clientErrorReport";

const MAX_REPORTS = 20;
const seen = new Set<string>();
let sent = 0;

function fingerprint(message: string, source: string): string {
  return `${source}:${message.slice(0, 120)}`;
}

function capture(error: unknown, source: string, appVersion: string) {
  const message = error instanceof Error ? error.message : String(error);
  const key = fingerprint(message, source);
  if (seen.has(key) || sent >= MAX_REPORTS) return;
  seen.add(key);
  sent += 1;
  void reportClientError(error, {
    source,
    app_version: appVersion,
    url: import.meta.client ? window.location.pathname : undefined,
  });
}

export default defineNuxtPlugin((nuxtApp) => {
  if (import.meta.dev) return;

  const appVersion = String(useRuntimeConfig().public.appVersion ?? "");

  nuxtApp.hook("vue:error", (error) => capture(error, "vue", appVersion));
  nuxtApp.hook("app:error", (error) => capture(error, "app", appVersion));

  if (import.meta.client) {
    window.addEventListener("unhandledrejection", (event) => capture(event.reason, "promise", appVersion));
    window.addEventListener("error", (event) => capture(event.error ?? event.message, "window", appVersion));
  }
});
