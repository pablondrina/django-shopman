## O que muda

<!-- Descreva resumidamente o que esta PR faz e por quê. -->

## Checklist Omotenashi

- [ ] **Copy**: mudanças em texto UI usam `{% omotenashi KEY %}`, ou têm `{# copy-ok: <razão> #}` justificando a exceção.
- [ ] **5 testes Omotenashi**: invisível (zero onclick/document.*), antecipação (dado conhecido pré-preenchido), ma (espaço em branco generoso), calor (tom acolhedor, sem formalidade), retorno (cliente recorrente recebe sinal de reconhecimento).
- [ ] **Acessibilidade**: contraste ≥ AAA em copy principal; touch targets ≥ 48 px; heading levels corretos (sem pulos de h1→h3).
- [ ] **Mobile-first**: testado em viewport 375 px (iPhone SE); nada quebrado em telas pequenas.
- [ ] **HTMX ↔ servidor / Alpine ↔ DOM**: zero `onclick=`, `onchange=`, `document.getElementById`, `classList.toggle/add/remove` em templates; toda comunicação com servidor via HTMX; todo estado local via Alpine.
