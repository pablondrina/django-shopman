import { posApiPath } from "~/utils/api";

export function usePosApiPath() {
  const baseURL = useRuntimeConfig().app.baseURL || "/";
  return (path: string) => posApiPath(path, baseURL);
}
