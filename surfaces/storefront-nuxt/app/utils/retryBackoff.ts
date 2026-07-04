import { isTransientError } from './httpError'

export interface BackoffOptions {
  // Tentativas ADICIONAIS após a primeira (default 2 → até 3 execuções no total).
  retries?: number
  baseMs?: number
  maxMs?: number
  // Decide se vale re-tentar dado o erro e o número da tentativa (0-based).
  shouldRetry?: (error: unknown, attempt: number) => boolean
  // Injetáveis para teste determinístico (jitter fixo, sleep sem timers reais).
  jitter?: () => number
  sleep?: (ms: number) => Promise<void>
}

const defaultSleep = (ms: number) => new Promise<void>(resolve => setTimeout(resolve, ms))

// Backoff exponencial com jitter e teto, e um cap de tentativas: sobrevive a um
// soluço de rede sem martelar o servidor, e falha LOUD (propaga o erro) quando o
// problema persiste — nunca engole silenciosamente.
export async function retryWithBackoff<T> (fn: () => Promise<T>, opts: BackoffOptions = {}): Promise<T> {
  const retries = opts.retries ?? 2
  const baseMs = opts.baseMs ?? 200
  const maxMs = opts.maxMs ?? 2000
  const shouldRetry = opts.shouldRetry ?? isTransientError
  const jitter = opts.jitter ?? Math.random
  const sleep = opts.sleep ?? defaultSleep

  let attempt = 0
  for (;;) {
    try {
      return await fn()
    } catch (error) {
      if (attempt >= retries || !shouldRetry(error, attempt)) throw error
      const exp = Math.min(maxMs, baseMs * 2 ** attempt)
      // Full jitter: espalha os retries de vários clientes, evita thundering herd.
      const delay = Math.round(exp * jitter())
      await sleep(delay)
      attempt += 1
    }
  }
}
