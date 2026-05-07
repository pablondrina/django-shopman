import {
  appendResponseHeader,
  getQuery,
  getRequestHeader,
  readRawBody,
  setResponseStatus,
  type H3Event
} from 'h3'
import { withQuery } from 'ufo'

export async function proxyDjangoApi (event: H3Event, path: string) {
  const config = useRuntimeConfig(event)
  const method = event.method || 'GET'
  const normalizedPath = path.endsWith('/') ? path : `${path}/`
  const target = withQuery(
    `${config.djangoBaseUrl}/api/v1/${normalizedPath}`,
    getQuery(event)
  )

  const headers: Record<string, string> = {
    accept: getRequestHeader(event, 'accept') || 'application/json'
  }

  const cookie = getRequestHeader(event, 'cookie')
  if (cookie) headers.cookie = cookie

  const contentType = getRequestHeader(event, 'content-type')
  if (contentType) headers['content-type'] = contentType

  const origin = getRequestHeader(event, 'origin')
  if (origin) headers.origin = origin

  const referer = getRequestHeader(event, 'referer')
  if (referer) headers.referer = referer

  const csrfCookie = cookie
    ?.split(';')
    .map(part => part.trim())
    .find(part => part.startsWith('csrftoken='))
    ?.slice('csrftoken='.length)
  if (csrfCookie) headers['x-csrftoken'] = decodeURIComponent(csrfCookie)

  const body = ['GET', 'HEAD'].includes(method)
    ? undefined
    : await readRawBody(event, false)

  const response = await $fetch.raw(target, {
    method,
    headers,
    body,
    ignoreResponseError: true
  })

  const setCookie = response.headers.get('set-cookie')
  if (setCookie) appendResponseHeader(event, 'set-cookie', setCookie)

  const contentTypeResponse = response.headers.get('content-type')
  if (contentTypeResponse) appendResponseHeader(event, 'content-type', contentTypeResponse)

  setResponseStatus(event, response.status)
  return response._data
}
