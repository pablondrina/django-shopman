export function useCountdown (deadlineIso: MaybeRefOrGetter<string | null | undefined>) {
  const remaining = ref(0)
  let timer: ReturnType<typeof setInterval> | null = null

  function compute () {
    const iso = toValue(deadlineIso)
    if (!iso) {
      remaining.value = 0
      return
    }
    const target = new Date(iso).getTime()
    if (Number.isNaN(target)) {
      remaining.value = 0
      return
    }
    remaining.value = Math.max(0, Math.floor((target - Date.now()) / 1000))
  }

  function start () {
    stop()
    compute()
    timer = setInterval(compute, 1000)
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
    watch(() => toValue(deadlineIso), () => compute())
  }

  const expired = computed(() => remaining.value <= 0)
  const formatted = computed(() => {
    const total = remaining.value
    if (total <= 0) return '00:00'
    const minutes = Math.floor(total / 60)
    const seconds = total % 60
    if (minutes >= 60) {
      const hours = Math.floor(minutes / 60)
      const mins = minutes % 60
      return `${String(hours).padStart(2, '0')}:${String(mins).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
    }
    return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
  })

  return { remaining, expired, formatted, start, stop }
}
