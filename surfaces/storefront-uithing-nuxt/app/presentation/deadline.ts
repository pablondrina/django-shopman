// Timeouts transparentes: helpers puros de contagem regressiva ancorados no
// relógio do servidor. Todo TTL que afeta o cliente (expiração do PIX, deadline
// de confirmação) precisa de countdown vivo. `nowMs` entra por parâmetro para
// manter as funções puras e testáveis (mesmo padrão de cart.ts/holdCountdown).

// Diferença servidor−cliente. A UI alinha seu relógio ao do servidor para que o
// countdown não derrape se o relógio do dispositivo estiver errado.
export function serverClockOffsetMs (serverNowIso: string | null | undefined, clientNowMs: number): number {
  if (!serverNowIso) return 0
  const server = Date.parse(serverNowIso)
  if (Number.isNaN(server)) return 0
  return server - clientNowMs
}

export interface DeadlineCountdown {
  totalSeconds: number
  mmss: string
  isExpired: boolean
}

// Contagem mm:ss até o deadline, clampada em zero. Acima de 1h ainda exibe em
// minutos (ex.: 60:00 para o PIX padrão de 1h) — sem horas, por simplicidade.
export function deadlineCountdown (deadlineIso: string | null | undefined, nowMs: number): DeadlineCountdown | null {
  if (!deadlineIso) return null
  const deadline = Date.parse(deadlineIso)
  if (Number.isNaN(deadline)) return null
  const totalSeconds = Math.max(0, Math.floor((deadline - nowMs) / 1000))
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  const pad = (value: number) => String(value).padStart(2, '0')
  return { totalSeconds, mmss: `${pad(minutes)}:${pad(seconds)}`, isExpired: totalSeconds === 0 }
}

// Percentual restante (0..100) numa janela conhecida. Para a barra do PIX a
// janela é o tempo restante no primeiro render (anchor): a barra drena de cheia
// a vazia honestamente, sem depender do início real do intent (que a projeção
// não expõe).
export function countdownPct (remainingSeconds: number, windowSeconds: number): number {
  if (windowSeconds <= 0) return 0
  return Math.max(0, Math.min(100, Math.round((remainingSeconds / windowSeconds) * 100)))
}

export const URGENT_THRESHOLD_PCT = 20

export function isCountdownUrgent (pct: number): boolean {
  return pct <= URGENT_THRESHOLD_PCT
}
