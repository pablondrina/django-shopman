import { shopmanApiPath } from '~/utils/shopmanApi'

export function useShopmanApiPath () {
  const baseURL = useRuntimeConfig().app.baseURL || '/'

  return (path: string) => shopmanApiPath(path, baseURL)
}
