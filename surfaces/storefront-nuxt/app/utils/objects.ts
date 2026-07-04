// Remove uma chave de um mapa retornando um objeto NOVO (imutável), sem o
// `delete obj[key]` dinâmico (que o TS não estreita e o lint proíbe). Usado nos
// mapas de estado por-chave (pending por sku/ref, toggles de preferência).
export function omitKey<K extends PropertyKey, V> (obj: Record<K, V>, key: K): Record<K, V> {
  const { [key]: _omitted, ...rest } = obj
  return rest as Record<K, V>
}

// Coage um valor desconhecido (payload de API) a um record indexável para leitura
// defensiva, sem espalhar `any`. Valores lidos seguem `unknown` → o call-site
// valida cada campo (typeof/String/numberOrNull).
export function asRecord (value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' ? (value as Record<string, unknown>) : {}
}
