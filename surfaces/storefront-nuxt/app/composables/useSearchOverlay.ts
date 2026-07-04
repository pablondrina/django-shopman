import { ref } from 'vue'

// Estado do overlay de busca (singleton de módulo, compartilhado entre o gatilho e o
// próprio overlay). O input é registrado pelo overlay; openSearch() o foca de forma
// SÍNCRONA — chamado dentro do gesto de toque do gatilho —, e só depois revela o
// overlay. É isso que faz o iOS abrir o teclado (foco na mesma tela, dentro do gesto;
// foco após navegação de página é bloqueado pelo Safari).
const open = ref(false)
let inputEl: HTMLInputElement | null = null

export function useSearchOverlay () {
  function registerInput (el: HTMLInputElement | null) {
    inputEl = el
  }
  function openSearch () {
    // Foco PRIMEIRO (síncrono, dentro do gesto) — o input está sempre no DOM e focável
    // (escondido por opacidade, não display:none). Depois revela.
    inputEl?.focus()
    open.value = true
  }
  function closeSearch () {
    open.value = false
    inputEl?.blur()
  }
  return { open, registerInput, openSearch, closeSearch }
}
