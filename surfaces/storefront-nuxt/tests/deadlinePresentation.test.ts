import { describe, expect, it } from 'vitest'
import { countdownPct, deadlineCountdown, isCountdownUrgent, serverClockOffsetMs, URGENT_THRESHOLD_PCT } from '~/presentation/deadline'

const deadline = '2026-06-14T12:00:00+00:00'

describe('deadline presentation — serverClockOffsetMs', () => {
  it('computes server−client skew and falls back to zero', () => {
    expect(serverClockOffsetMs('2026-06-14T12:00:30+00:00', Date.parse('2026-06-14T12:00:00+00:00'))).toBe(30000)
    expect(serverClockOffsetMs(null, 0)).toBe(0)
    expect(serverClockOffsetMs('garbage', 1234)).toBe(0)
  })
})

describe('deadline presentation — deadlineCountdown', () => {
  it('counts down mm:ss and clamps at zero', () => {
    expect(deadlineCountdown(deadline, Date.parse(deadline) - (5 * 60 + 7) * 1000))
      .toEqual({ totalSeconds: 307, mmss: '05:07', isExpired: false })
    expect(deadlineCountdown(deadline, Date.parse(deadline) - 60 * 60 * 1000)?.mmss).toBe('60:00')
    expect(deadlineCountdown(deadline, Date.parse(deadline) + 5000))
      .toEqual({ totalSeconds: 0, mmss: '00:00', isExpired: true })
  })

  it('returns null for missing or invalid input', () => {
    expect(deadlineCountdown(null, 0)).toBeNull()
    expect(deadlineCountdown('not-a-date', 0)).toBeNull()
  })
})

describe('deadline presentation — progress', () => {
  it('computes remaining percent clamped to 0..100', () => {
    expect(countdownPct(300, 600)).toBe(50)
    expect(countdownPct(600, 600)).toBe(100)
    expect(countdownPct(0, 600)).toBe(0)
    expect(countdownPct(700, 600)).toBe(100)
    expect(countdownPct(60, 0)).toBe(0)
  })

  it('flags urgency at or below the threshold', () => {
    expect(isCountdownUrgent(URGENT_THRESHOLD_PCT)).toBe(true)
    expect(isCountdownUrgent(URGENT_THRESHOLD_PCT - 1)).toBe(true)
    expect(isCountdownUrgent(URGENT_THRESHOLD_PCT + 1)).toBe(false)
    expect(isCountdownUrgent(100)).toBe(false)
  })
})
