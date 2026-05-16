export default defineEventHandler((event) => {
  const url = getRequestURL(event)
  setResponseHeader(event, 'Content-Type', 'text/plain; charset=utf-8')
  return `User-agent: *
Allow: /
Disallow: /checkout
Disallow: /cart
Disallow: /conta
Disallow: /pedido/
Disallow: /tracking/

Sitemap: ${url.origin}/sitemap.xml
`
})
