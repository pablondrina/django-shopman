// Canonical = origin + caminho SEM query string. Em páginas de listagem
// (menu/busca) isso colapsa variantes de filtro (?filtro=, ?secao=) numa única
// URL canônica — evita duplicate content (lacuna do SEO-PLAN). SSR-safe via
// useRequestURL (reflete o host da request no servidor).
export function useCanonical (): void {
  const requestUrl = useRequestURL()
  const route = useRoute()
  useHead({
    link: [{ rel: 'canonical', href: () => `${requestUrl.origin}${route.path}` }]
  })
}
