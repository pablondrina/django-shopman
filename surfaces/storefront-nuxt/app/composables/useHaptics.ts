type HapticPattern = 'light' | 'double' | 'confirm' | 'error' | number | number[]

const HAPTIC_PATTERNS = {
  light: 10,
  double: [30, 20, 30],
  confirm: [50, 30, 50],
  error: 100
} satisfies Record<string, number | number[]>

function patternValue (pattern: HapticPattern = 'light') {
  if (typeof pattern === 'string') return HAPTIC_PATTERNS[pattern] || HAPTIC_PATTERNS.light
  return pattern
}

export function useHaptics () {
  function triggerHaptic (pattern: HapticPattern = 'light') {
    if (import.meta.server || !navigator.vibrate) return false
    try {
      return navigator.vibrate(patternValue(pattern))
    } catch {
      return false
    }
  }

  return {
    triggerHaptic,
    light: () => triggerHaptic('light'),
    double: () => triggerHaptic('double'),
    confirm: () => triggerHaptic('confirm'),
    error: () => triggerHaptic('error')
  }
}
