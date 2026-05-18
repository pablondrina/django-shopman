import { spawn, spawnSync } from 'node:child_process'
import { mkdtemp } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const baseUrl = (process.env.SHOPMAN_THING_URL || 'http://127.0.0.1:3003').replace(/\/$/, '')
const port = Number(process.env.SHOPMAN_CHROME_PORT || 9243)
const failures = []

function assert (condition, message) {
  if (!condition) failures.push(message)
}

async function wait (ms) {
  await new Promise(resolve => setTimeout(resolve, ms))
}

async function waitForHttp (url, timeoutMs = 10000) {
  const started = Date.now()
  while (Date.now() - started < timeoutMs) {
    try {
      const response = await fetch(url, { signal: AbortSignal.timeout(5000) })
      if (response.ok) return response
    } catch {}
    await wait(200)
  }
  throw new Error(`Timed out waiting for ${url}`)
}

function findChrome () {
  const candidates = [
    process.env.CHROME_BIN,
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
    'google-chrome',
    'chromium',
    'chromium-browser',
  ].filter(Boolean)

  for (const candidate of candidates) {
    if (candidate.includes('/')) return candidate
    const found = spawnSync('which', [candidate], { encoding: 'utf8' })
    if (found.status === 0) return found.stdout.trim()
  }
  throw new Error('Chrome/Chromium not found. Set CHROME_BIN to run UX smoke.')
}

async function launchChrome () {
  const chrome = findChrome()
  const profile = await mkdtemp(join(tmpdir(), 'shopman-thing-ux-'))
  const child = spawn(chrome, [
    '--headless=new',
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${profile}`,
    '--disable-gpu',
    '--no-first-run',
    '--no-default-browser-check',
  ], { stdio: 'ignore' })

  await waitForHttp(`http://127.0.0.1:${port}/json/version`)
  return child
}

async function connectCdp () {
  const response = await fetch(`http://127.0.0.1:${port}/json/new`, { method: 'PUT' })
  const target = await response.json()
  const ws = new WebSocket(target.webSocketDebuggerUrl)
  let nextId = 1
  const pending = new Map()
  const listeners = new Map()

  ws.onmessage = event => {
    const message = JSON.parse(event.data)
    if (message.id && pending.has(message.id)) {
      const { resolve, reject } = pending.get(message.id)
      pending.delete(message.id)
      if (message.error) reject(new Error(JSON.stringify(message.error)))
      else resolve(message.result)
      return
    }
    if (message.method && listeners.has(message.method)) {
      for (const listener of listeners.get(message.method)) listener(message.params || {})
    }
  }

  await new Promise((resolve, reject) => {
    ws.onopen = resolve
    ws.onerror = reject
  })

  function send (method, params = {}) {
    return new Promise((resolve, reject) => {
      const id = nextId++
      const timer = setTimeout(() => {
        pending.delete(id)
        reject(new Error(`CDP command timed out: ${method}`))
      }, 15000)
      pending.set(id, {
        resolve: value => {
          clearTimeout(timer)
          resolve(value)
        },
        reject: error => {
          clearTimeout(timer)
          reject(error)
        },
      })
      ws.send(JSON.stringify({ id, method, params }))
    })
  }

  function on (method, listener) {
    if (!listeners.has(method)) listeners.set(method, [])
    listeners.get(method).push(listener)
  }

  return { send, on, close: () => ws.close() }
}

async function evaluate (cdp, expression) {
  const result = await cdp.send('Runtime.evaluate', {
    expression,
    awaitPromise: true,
    returnByValue: true,
  })
  if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails))
  return result.result.value
}

async function openPage (path, viewport) {
  const cdp = await connectCdp()
  await cdp.send('Page.enable')
  await cdp.send('Runtime.enable')
  await cdp.send('Network.enable')
  await cdp.send('Emulation.setDeviceMetricsOverride', {
    width: viewport.width,
    height: viewport.height,
    deviceScaleFactor: viewport.deviceScaleFactor || 1,
    mobile: !!viewport.mobile,
  })
  await cdp.send('Page.navigate', { url: `${baseUrl}${path}` })
  await wait(1800)
  return cdp
}

function pageProbe () {
  return `(() => {
    const visible = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length) && getComputedStyle(el).visibility !== 'hidden'
    return {
      text: document.body.innerText,
      h1: [...document.querySelectorAll('h1')].filter(visible).map(el => el.innerText.trim()),
      tabs: [...document.querySelectorAll('[data-slot="tabs-trigger"]')].filter(visible).map(el => ({
        label: el.innerText.trim(),
        selected: el.getAttribute('aria-selected') === 'true',
        state: el.getAttribute('data-state'),
      })),
      searchInputs: [...document.querySelectorAll('input[placeholder]')].filter(visible).map(el => el.placeholder).filter(Boolean),
    }
  })()`
}

async function clickHeroTab (cdp, label) {
  return evaluate(cdp, `(async () => {
    const tab = [...document.querySelectorAll('[data-slot="tabs-trigger"]')].find(el => el.innerText.trim() === ${JSON.stringify(label)})
    if (!tab) return { clicked: false, h1: [] }
    tab.click()
    await new Promise(resolve => setTimeout(resolve, 250))
    const visible = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length) && getComputedStyle(el).visibility !== 'hidden'
    return {
      clicked: true,
      selected: tab.getAttribute('aria-selected') === 'true' || tab.getAttribute('data-state') === 'active',
      h1: [...document.querySelectorAll('h1')].filter(visible).map(el => el.innerText.trim()),
    }
  })()`)
}

async function dispatchClickRectCenter (cdp, selector) {
  const rect = await evaluate(cdp, `(() => {
    const el = document.querySelector(${JSON.stringify(selector)})
    if (!el) return null
    el.scrollIntoView({ block: 'center', inline: 'center' })
    const r = el.getBoundingClientRect()
    return { x: r.x + r.width / 2, y: r.y + r.height / 2, w: r.width, h: r.height }
  })()`)
  if (!rect) return false
  await wait(150)
  await cdp.send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: rect.x, y: rect.y })
  await cdp.send('Input.dispatchMouseEvent', { type: 'mousePressed', x: rect.x, y: rect.y, button: 'left', clickCount: 1 })
  await cdp.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: rect.x, y: rect.y, button: 'left', clickCount: 1 })
  return true
}

async function run () {
  await waitForHttp(baseUrl)
  const chrome = await launchChrome()
  try {
    const home = await openPage('/', { width: 390, height: 844, deviceScaleFactor: 2, mobile: true })
    const homeState = await evaluate(home, pageProbe())
    assert(!(homeState.text.includes('Loja aberta') && homeState.text.includes('Loja em pausa')), 'home shows open and paused status at the same time')
    assert(['Agora', 'Pedir', 'Forno'].every(label => homeState.tabs.some(tab => tab.label === label)), 'home hero does not expose the expected distinct moments')

    const heroTitles = []
    for (const label of ['Agora', 'Pedir', 'Forno']) {
      const state = await clickHeroTab(home, label)
      assert(state.clicked, `home hero tab ${label} was not clickable`)
      assert(state.selected, `home hero tab ${label} did not become active`)
      heroTitles.push(state.h1[0] || '')
    }
    assert(new Set(heroTitles).size >= 2, 'home hero moments are visually collapsed into one title')
    home.close()

    const menu = await openPage('/menu', { width: 390, height: 844, deviceScaleFactor: 2, mobile: true })
    const requests = []
    cdpRequestCapture(menu, requests)
    const menuState = await evaluate(menu, pageProbe())
    assert(menuState.searchInputs.length === 1, `menu should show exactly one text search, found ${menuState.searchInputs.length}`)
    await evaluate(menu, `(() => {
      const input = document.querySelector('input[placeholder]')
      input.value = 'croissant'
      input.dispatchEvent(new Event('input', { bubbles: true }))
    })()`)
    await wait(300)
    const clicked = await dispatchClickRectCenter(menu, '[data-slot="number-field-increment"]')
    assert(clicked, 'menu quantity increment was not found')
    await wait(1500)
    const afterCart = await evaluate(menu, pageProbe())
    const cartMutations = requests.filter(request => request.url.includes('/api/v1/cart/skus/'))
    assert(cartMutations.length >= 1, 'menu quantity increment did not call the canonical cart sku endpoint')
    assert(cartMutations.every(request => request.method === 'PUT'), 'menu quantity increment used a non-canonical cart method')
    assert(cartMutations.every(request => !request.status || request.status < 400), 'menu quantity increment returned a failed cart response')
    assert(!afterCart.text.toLowerCase().includes('estoque insuficiente'), 'menu quantity increment surfaced insufficient stock for a projected available item')
    menu.close()
  } finally {
    chrome.kill()
  }

  if (failures.length) {
    console.error(`UX smoke failed:\\n- ${failures.join('\\n- ')}`)
    process.exit(1)
  }
  console.log('UX smoke passed')
}

function cdpRequestCapture (cdp, requests) {
  const byId = new Map()
  cdp.on('Network.requestWillBeSent', params => {
    byId.set(params.requestId, {
      url: params.request.url,
      method: params.request.method,
      postData: params.request.postData || '',
      status: null,
    })
  })
  cdp.on('Network.responseReceived', params => {
    const item = byId.get(params.requestId)
    if (!item) return
    item.status = params.response.status
    requests.push(item)
  })
}

run().catch(error => {
  console.error(error)
  process.exit(1)
})
