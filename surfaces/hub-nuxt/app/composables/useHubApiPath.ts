import { hubApiPath } from "~/utils/api";

export function useHubApiPath() {
  const baseURL = useRuntimeConfig().app.baseURL || "/";
  return (path: string) => hubApiPath(path, baseURL);
}
