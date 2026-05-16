export default defineEventHandler((event) => {
  const url = getRequestURL(event)
  const routes = ['/', '/menu', '/como-funciona']
  setResponseHeader(event, 'Content-Type', 'application/xml; charset=utf-8')
  return `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${routes.map((route) => `  <url><loc>${url.origin}${route}</loc></url>`).join('\n')}
</urlset>
`
})
