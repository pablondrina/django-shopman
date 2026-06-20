// robots.txt domain-aware: o host vem do request (funciona em dev e em qualquer
// domínio de produção sem hardcode). Bloqueia rotas privadas/transacionais e
// aponta o sitemap.
export default defineEventHandler((event) => {
  const origin = getRequestURL(event).origin
  setHeader(event, 'content-type', 'text/plain; charset=utf-8')
  return [
    'User-agent: *',
    'Allow: /',
    'Disallow: /conta',
    'Disallow: /finalizar',
    'Disallow: /sacola',
    'Disallow: /entrar',
    'Disallow: /pedido/',
    'Disallow: /api/',
    '',
    `Sitemap: ${origin}/sitemap.xml`,
    ''
  ].join('\n')
})
