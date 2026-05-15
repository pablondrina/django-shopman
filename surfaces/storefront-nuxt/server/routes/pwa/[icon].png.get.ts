import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'

const ICON_FILES: Record<string, string> = {
  'icon-192': 'icon-192.png',
  'icon-512': 'icon-512.png',
  'icon-maskable-512': 'icon-maskable-512.png'
}

function pngResponse (event: Parameters<typeof setResponseHeader>[0], body: Uint8Array) {
  setResponseHeader(event, 'Content-Type', 'image/png')
  setResponseHeader(event, 'Cache-Control', 'public, max-age=86400, immutable')
  return body
}

export default defineEventHandler(async (event) => {
  const rawIcon = event.context.params?.icon || Object.values(event.context.params || {})[0] || ''
  const icon = String(rawIcon).replace(/\.png$/, '')
  const filename = ICON_FILES[icon]
  if (!filename) {
    throw createError({ statusCode: 404, statusMessage: 'PWA icon not found' })
  }

  try {
    return pngResponse(event, await readFile(resolve(process.cwd(), 'public', 'pwa', filename)))
  } catch {
    // Fall back to the canonical Django asset when the Nuxt public copy is unavailable.
  }

  const config = useRuntimeConfig(event)
  const response = await $fetch.raw<ArrayBuffer>(`${config.djangoBaseUrl}/static/storefront/${filename}`, {
    responseType: 'arrayBuffer'
  })

  return pngResponse(event, new Uint8Array(response._data))
})
