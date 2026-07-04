import { isTransientError } from "./httpError";

export interface RetryOptions {
  /** Máximo de tentativas totais (inclui a primeira). Default 3. */
  attempts?: number;
  /** Atraso base em ms (1ª retentativa). Default 300. */
  baseDelayMs?: number;
  /** Teto do atraso em ms. Default 4000. */
  capMs?: number;
  /** Decide se um erro merece retry. Default: `isTransientError`. */
  shouldRetry?: (error: unknown) => boolean;
  /** Injetável para teste (sem timers reais / sem aleatoriedade). */
  sleep?: (ms: number) => Promise<void>;
  jitter?: (max: number) => number;
}

const defaultSleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));
const defaultJitter = (max: number) => Math.random() * max;

/**
 * Executa `fn` com backoff exponencial + jitter e teto. Só retenta erros que
 * `shouldRetry` aprova (transientes por default). Esgotadas as tentativas, propaga o
 * último erro — fail-loud, nunca engole ([[feedback_validate_early_inline]]).
 */
export async function retryWithBackoff<T>(fn: () => Promise<T>, options: RetryOptions = {}): Promise<T> {
  const attempts = Math.max(1, options.attempts ?? 3);
  const baseDelayMs = options.baseDelayMs ?? 300;
  const capMs = options.capMs ?? 4000;
  const shouldRetry = options.shouldRetry ?? isTransientError;
  const sleep = options.sleep ?? defaultSleep;
  const jitter = options.jitter ?? defaultJitter;

  let lastError: unknown;
  for (let attempt = 1; attempt <= attempts; attempt++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error;
      if (attempt >= attempts || !shouldRetry(error)) throw error;
      const exponential = Math.min(capMs, baseDelayMs * 2 ** (attempt - 1));
      await sleep(exponential + jitter(exponential));
    }
  }
  throw lastError;
}
