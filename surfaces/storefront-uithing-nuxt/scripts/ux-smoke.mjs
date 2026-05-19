import { spawn, spawnSync } from 'node:child_process'
import { mkdtemp } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const baseUrl = (process.env.SHOPMAN_THING_URL || 'http://127.0.0.1:3003/thing').replace(/\/$/, '')
const port = Number(process.env.SHOPMAN_CHROME_PORT || 9243)
const cdpTimeoutMs = Number(process.env.SHOPMAN_CDP_TIMEOUT_MS || 15000)
const traceUx = process.env.SHOPMAN_UX_TRACE === '1'
const failures = []

function trace (message) {
  if (traceUx) console.error(`[ux-smoke] ${message}`)
}

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
      }, cdpTimeoutMs)
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

async function waitForProbe (cdp, description, predicate, timeoutMs = 8000) {
  const started = Date.now()
  let lastState = null
  while (Date.now() - started < timeoutMs) {
    lastState = await evaluate(cdp, pageProbe())
    if (predicate(lastState)) return lastState
    await wait(250)
  }
  throw new Error(`Timed out waiting for ${description}: ${JSON.stringify(lastState)}`)
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
    const body = document.body
    return {
      url: location.href,
      text: body ? body.innerText : '',
      h1: [...document.querySelectorAll('h1')].filter(visible).map(el => el.innerText.trim()),
      buttons: [...document.querySelectorAll('button,a')].filter(visible).map(el => el.innerText.trim()).filter(Boolean),
      tabs: [...document.querySelectorAll('[data-slot="tabs-trigger"]')].filter(visible).map(el => ({
        label: el.innerText.trim(),
        selected: el.getAttribute('aria-selected') === 'true',
        state: el.getAttribute('data-state'),
      })),
      searchInputs: [...document.querySelectorAll('input[placeholder]')].filter(visible).map(el => el.placeholder).filter(Boolean),
      menuSearchButtons: [...document.querySelectorAll('button[aria-label="Buscar no cardápio"]')].filter(visible).length,
      productTiles: document.querySelectorAll('[data-slot="card"]').length,
      quantityControls: document.querySelectorAll('[data-slot="number-field"]').length,
      tabContents: document.querySelectorAll('[data-slot="tabs-content"]').length,
      domNodes: document.querySelectorAll('*').length,
    }
  })()`
}

async function clickHeroTab (cdp, label) {
  const rect = await evaluate(cdp, `(() => {
    const tab = [...document.querySelectorAll('[data-slot="tabs-trigger"]')].find(el => el.innerText.trim() === ${JSON.stringify(label)})
    if (!tab) return null
    tab.scrollIntoView({ block: 'center', inline: 'center' })
    const r = tab.getBoundingClientRect()
    return { x: r.x + r.width / 2, y: r.y + r.height / 2, w: r.width, h: r.height }
  })()`)
  if (!rect) return { clicked: false, h1: [] }
  await wait(150)
  await cdp.send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: rect.x, y: rect.y })
  await cdp.send('Input.dispatchMouseEvent', { type: 'mousePressed', x: rect.x, y: rect.y, button: 'left', clickCount: 1 })
  await cdp.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: rect.x, y: rect.y, button: 'left', clickCount: 1 })
  await wait(350)
  let state = await evaluate(cdp, `(() => {
    const tab = [...document.querySelectorAll('[data-slot="tabs-trigger"]')].find(el => el.innerText.trim() === ${JSON.stringify(label)})
    const visible = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length) && getComputedStyle(el).visibility !== 'hidden'
    return {
      clicked: true,
      selected: !!tab && (tab.getAttribute('aria-selected') === 'true' || tab.getAttribute('data-state') === 'active'),
      h1: [...document.querySelectorAll('h1')].filter(visible).map(el => el.innerText.trim()),
    }
  })()`)
  if (!state.selected) {
    await evaluate(cdp, `(() => {
      const tab = [...document.querySelectorAll('[data-slot="tabs-trigger"]')].find(el => el.innerText.trim() === ${JSON.stringify(label)})
      if (tab) tab.click()
      return true
    })()`)
    await wait(350)
    state = await evaluate(cdp, `(() => {
      const tab = [...document.querySelectorAll('[data-slot="tabs-trigger"]')].find(el => el.innerText.trim() === ${JSON.stringify(label)})
      const visible = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length) && getComputedStyle(el).visibility !== 'hidden'
      return {
        clicked: true,
        selected: !!tab && (tab.getAttribute('aria-selected') === 'true' || tab.getAttribute('data-state') === 'active'),
        h1: [...document.querySelectorAll('h1')].filter(visible).map(el => el.innerText.trim()),
      }
    })()`)
  }
  return state
}

async function dispatchClickRectCenter (cdp, selector) {
  const found = await evaluate(cdp, `(() => {
    const visible = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length) && getComputedStyle(el).visibility !== 'hidden'
    const el = [...document.querySelectorAll(${JSON.stringify(selector)})].find(visible)
    if (!el) return false
    el.scrollIntoView({ block: 'center', inline: 'center', behavior: 'auto' })
    return true
  })()`)
  if (!found) return false
  await wait(250)
  const rect = await evaluate(cdp, `(() => {
    const visible = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length) && getComputedStyle(el).visibility !== 'hidden'
    const el = [...document.querySelectorAll(${JSON.stringify(selector)})].find(visible)
    if (!el) return null
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

async function dispatchClickButtonText (cdp, text) {
  const clicked = await evaluate(cdp, `(() => {
    const visible = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length) && getComputedStyle(el).visibility !== 'hidden'
    const el = [...document.querySelectorAll('button')].find(button => visible(button) && button.innerText.trim() === ${JSON.stringify(text)})
    if (!el) return false
    el.scrollIntoView({ block: 'center', inline: 'center', behavior: 'auto' })
    el.click()
    return true
  })()`)
  if (clicked) await wait(250)
  return clicked
}

async function run () {
  await waitForHttp(baseUrl)
  const chrome = await launchChrome()
  try {
    trace('open mobile home')
    const home = await openPage('/', { width: 390, height: 844, deviceScaleFactor: 2, mobile: true })
    trace('probe mobile home')
    const homeState = await evaluate(home, pageProbe())
    assert(!(homeState.text.includes('Loja aberta') && homeState.text.includes('Loja em pausa')), 'home shows open and paused status at the same time')
    assert(homeState.quantityControls === 0, `home initial render should show add buttons instead of zero quantity controls, found ${homeState.quantityControls}`)
    assert(homeState.tabContents === 0, `home should not mount hero tab panels, found ${homeState.tabContents}`)
    assert(homeState.tabs.length === 0, `home hero carousel should not be implemented with tabs, found ${homeState.tabs.length} tab triggers`)
    assert(homeState.domNodes < 3200, `home initial DOM is too large: ${homeState.domNodes} nodes`)
    assert(homeState.text.includes('Direto do forno'), 'home should expose the projected availability section')
    assert(homeState.text.includes('Como Funciona'), 'home should expose the projected how-it-works section')
    assert(homeState.text.includes('WhatsApp'), 'home should expose a single projected WhatsApp handoff section')
    const heroLayout = await evaluate(home, `(() => {
      const hero = document.querySelector('[data-home-hero-carousel]')
      const title = hero?.querySelector('h1')
      if (!hero || !title) return null
      const r = hero.getBoundingClientRect()
      return {
        x: Math.round(r.x),
        width: Math.round(r.width),
        height: Math.round(r.height),
        viewportWidth: window.innerWidth,
        viewportHeight: window.innerHeight,
        titleAlign: getComputedStyle(title).textAlign,
        dots: hero.querySelectorAll('[role="tab"]').length,
      }
    })()`)
    assert(heroLayout && heroLayout.x <= 1 && heroLayout.width >= heroLayout.viewportWidth - 2, `mobile home hero should be full-bleed, got ${JSON.stringify(heroLayout)}`)
    assert(heroLayout && heroLayout.height >= heroLayout.viewportHeight - 72, `mobile home hero should fill the visible viewport under the navbar, got ${JSON.stringify(heroLayout)}`)
    assert(heroLayout && heroLayout.titleAlign === 'center', `home hero copy should be centered, got ${JSON.stringify(heroLayout)}`)
    assert(heroLayout && heroLayout.dots >= 3, `home hero should expose carousel slide controls, got ${JSON.stringify(heroLayout)}`)
    const homeMobileDensity = await evaluate(home, `(() => {
      const whatsappSection = [...document.querySelectorAll('main > section')].find(section =>
        section.innerText.includes('WhatsApp') && section.querySelector('a[href*="wa.me"], a[href*="whatsapp"]')
      )
      const firstProductTile = document.querySelector('[data-product-tile]')
      const price = firstProductTile?.querySelector('.text-base.font-semibold')
      const action = firstProductTile ? [...firstProductTile.querySelectorAll('button')].find(button => button.innerText.includes('Adicionar')) : null
      const rect = el => {
        const r = el.getBoundingClientRect()
        return { top: Math.round(r.top), bottom: Math.round(r.bottom), left: Math.round(r.left), right: Math.round(r.right), width: Math.round(r.width), height: Math.round(r.height) }
      }
      return {
        whatsappPaddingTop: whatsappSection ? getComputedStyle(whatsappSection).paddingTop : null,
        whatsappPaddingBottom: whatsappSection ? getComputedStyle(whatsappSection).paddingBottom : null,
        product: firstProductTile && price && action ? {
          tile: rect(firstProductTile),
          price: rect(price),
          action: rect(action),
          sameRow: Math.abs((price.getBoundingClientRect().top + price.getBoundingClientRect().bottom) / 2 - (action.getBoundingClientRect().top + action.getBoundingClientRect().bottom) / 2) <= 18
        } : null,
      }
    })()`)
    assert(homeMobileDensity.whatsappPaddingTop === '0px' && homeMobileDensity.whatsappPaddingBottom === '0px', `mobile WhatsApp hero should not have outer vertical padding, got ${JSON.stringify(homeMobileDensity)}`)
    assert(homeMobileDensity.product?.sameRow, `mobile product tile price and add action should share a row when space allows, got ${JSON.stringify(homeMobileDensity)}`)
    home.close()

    trace('open desktop home')
    const desktopHome = await openPage('/', { width: 1280, height: 800, deviceScaleFactor: 1, mobile: false })
    trace('probe desktop home')
    const desktopHomeState = await evaluate(desktopHome, pageProbe())
    assert(!desktopHomeState.buttons.includes('Finalizar'), 'desktop header should not expose checkout as a global nav item')
    assert(desktopHomeState.text.includes('Horário') && desktopHomeState.text.includes('Contato'), 'desktop shell should render the web footer')
    desktopHome.close()

    trace('open product detail')
    const product = await openPage('/product/BAGUETE', { width: 390, height: 844, deviceScaleFactor: 2, mobile: true })
    trace('probe product detail')
    const productState = await evaluate(product, pageProbe())
    assert(productState.h1.some(title => title.includes('Baguete')), 'product detail route does not expose the product name as h1')
    assert(productState.quantityControls === 0, `product detail route should show add button before cart mutation, found ${productState.quantityControls} quantity controls`)
    assert(productState.buttons.includes('Adicionar'), 'product detail route does not expose an add-to-cart button before quantity editing')
    product.close()

    trace('open menu')
    const menu = await openPage('/menu', { width: 390, height: 844, deviceScaleFactor: 2, mobile: true })
    const requests = []
    cdpRequestCapture(menu, requests)
    trace('probe menu')
    const menuState = await evaluate(menu, pageProbe())
    assert(menuState.menuSearchButtons === 1, `menu should show one sticky search action, found ${menuState.menuSearchButtons}`)
    assert(menuState.searchInputs.length === 0, `menu should keep text search collapsed initially, found ${menuState.searchInputs.length}`)
    assert(menuState.tabContents === 0, `menu should not duplicate grids inside hidden tab panels, found ${menuState.tabContents} tab contents`)
    assert(menuState.quantityControls <= 5, `menu initial render mounted too many quantity controls: ${menuState.quantityControls}`)
    assert(menuState.domNodes < 4000, `menu initial DOM is too large: ${menuState.domNodes} nodes`)
    const searchOpened = await dispatchClickRectCenter(menu, 'button[aria-label="Buscar no cardápio"]')
    assert(searchOpened, 'menu sticky search action was not clickable')
    const searchOpenState = await waitForProbe(
      menu,
      'expanded menu search',
      state => state.searchInputs.length === 1,
      3000
    )
    assert(searchOpenState.searchInputs.length === 1, `menu expanded search should show one text search, found ${searchOpenState.searchInputs.length}`)
    const searchTyped = await evaluate(menu, `(() => {
      const input = document.querySelector('input[placeholder]')
      if (!input) return false
      input.value = 'croissant'
      input.dispatchEvent(new Event('input', { bubbles: true }))
      return true
    })()`)
    assert(searchTyped, 'menu expanded search input was not writable')
    await wait(300)
    const clicked = await dispatchClickRectCenter(menu, '[data-slot="number-field-increment"]')
      || await dispatchClickButtonText(menu, 'Adicionar')
    assert(clicked, 'menu add control was not found')
    await wait(1500)
    trace('probe menu after add')
    const afterCart = await evaluate(menu, pageProbe())
    const cartMutations = requests.filter(request => request.url.includes('/api/v1/cart/skus/'))
    assert(cartMutations.length >= 1, 'menu quantity increment did not call the canonical cart sku endpoint')
    assert(cartMutations.every(request => request.method === 'PUT'), 'menu quantity increment used a non-canonical cart method')
    assert(cartMutations.every(request => !request.status || request.status < 400), 'menu quantity increment returned a failed cart response')
    assert(!afterCart.text.toLowerCase().includes('estoque insuficiente'), 'menu quantity increment surfaced insufficient stock for a projected available item')
    assert(afterCart.buttons.includes('Carrinho'), 'cart page entry point should remain visible after add')
    assert(!afterCart.buttons.some(label => label.includes('Finalizar pedido') || label.includes('Confirmar agora')), 'cart page should not open automatically after add')
    menu.close()

    trace('open checkout')
    const checkout = await openPage('/checkout', { width: 390, height: 844, deviceScaleFactor: 2, mobile: true })
    trace('probe checkout')
    const checkoutState = await waitForProbe(
      checkout,
      'checkout login gate',
      state => state.url.includes('/thing/login?next=/checkout') && state.h1.some(title => title.toLowerCase().normalize('NFD').replace(/\p{Diacritic}/gu, '').includes('telefone') || title.toLowerCase().normalize('NFD').replace(/\p{Diacritic}/gu, '').includes('codigo'))
    )
    assert(checkoutState.url.includes('/thing/login?next=/checkout'), `anonymous checkout should follow projected auth action, got ${checkoutState.url}`)
    assert(checkoutState.h1.some(title => title.toLowerCase().normalize('NFD').replace(/\p{Diacritic}/gu, '').includes('telefone') || title.toLowerCase().normalize('NFD').replace(/\p{Diacritic}/gu, '').includes('codigo')), 'login gate should expose a visible h1')
    assert(checkoutState.buttons.some(label => label.includes('WhatsApp')), 'login gate should expose WhatsApp recovery/send action')
    checkout.close()
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
