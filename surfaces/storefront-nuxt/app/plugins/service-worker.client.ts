export default defineNuxtPlugin(() => {
  if (!('serviceWorker' in navigator)) return

  if (import.meta.dev) {
    navigator.serviceWorker.getRegistrations()
      .then((registrations) => Promise.all(registrations.map(registration => registration.unregister())))
      .catch(() => {})
    if ('caches' in window) {
      caches.keys()
        .then((keys) => Promise.all(keys.filter(key => key.startsWith('shopman-nuxt-')).map(key => caches.delete(key))))
        .catch(() => {})
    }
    return
  }

  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {
      // Service worker is an enhancement; navigation remains network-first.
    })
  })
})
