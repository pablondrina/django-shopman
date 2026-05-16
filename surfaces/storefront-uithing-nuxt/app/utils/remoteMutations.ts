export function newRemoteMutationKey (prefix: string): string {
  const randomId = import.meta.client && window.crypto?.randomUUID
    ? window.crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`
  return `${prefix}-${randomId}`
}
