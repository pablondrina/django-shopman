export function usePosAction() {
  const apiPath = usePosApiPath();

  function csrfHeader(): Record<string, string> {
    const token = useCookie("csrftoken").value || "";
    return token ? { "X-CSRFToken": token } : {};
  }

  async function call<T = unknown>(
    path: string,
    options: { method?: "POST" | "PUT" | "PATCH" | "DELETE"; body?: Record<string, unknown> } = {},
  ): Promise<T> {
    return await $fetch<T>(apiPath(path), {
      method: options.method || "POST",
      credentials: "include",
      headers: csrfHeader(),
      body: options.body,
    });
  }

  return { call };
}
