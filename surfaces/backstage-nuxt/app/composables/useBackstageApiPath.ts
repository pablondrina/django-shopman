import { backstageApiPath } from '~/utils/api'

export function useBackstageApiPath () {
  const baseURL = useRuntimeConfig().app.baseURL || '/'
  return (path: string) => backstageApiPath(path, baseURL)
}
