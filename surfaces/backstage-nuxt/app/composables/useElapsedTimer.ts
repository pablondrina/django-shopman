/**
 * Live elapsed timer based on a starting offset (in seconds) from server.
 * Increments by 1 each second on the client to avoid a poll for every tick.
 */
export function useElapsedTimer (initialSeconds: MaybeRefOrGetter<number>) {
  const elapsed = ref(toValue(initialSeconds))
  let timer: ReturnType<typeof setInterval> | null = null

  function start () {
    stop()
    elapsed.value = toValue(initialSeconds)
    timer = setInterval(() => {
      elapsed.value += 1
    }, 1000)
  }
  function stop () {
    if (timer) {
      clearInterval(timer)
      timer = null
    }
  }

  if (import.meta.client) {
    onMounted(start)
    onBeforeUnmount(stop)
    watch(() => toValue(initialSeconds), (next) => {
      elapsed.value = next
    })
  }

  const formatted = computed(() => {
    const s = elapsed.value
    if (s < 0) return '0:00'
    const mins = Math.floor(s / 60)
    const secs = s % 60
    if (mins >= 60) {
      const h = Math.floor(mins / 60)
      const m = mins % 60
      return `${h}:${String(m).padStart(2, '0')}:${String(secs).padStart(2, '0')}`
    }
    return `${mins}:${String(secs).padStart(2, '0')}`
  })

  return { elapsed, formatted, start, stop }
}
