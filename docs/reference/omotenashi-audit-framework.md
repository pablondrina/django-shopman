# Omotenashi Audit Framework

Framework rigoroso para auditoria de qualidade omotenashi em qualquer superfície do Django Shopman.

**Princípio:** omotenashi digital não é copy calorosa nem adornos visuais. É hospitalidade
estrutural — o sistema SABE quem você é, ANTECIPA o que você precisa, e REMOVE atrito antes
que você o encontre. O esforço é invisível. O resultado é natural.

Referências:
- [`docs/omotenashi.md`](../omotenashi.md) — framework filosófico completo (Três Portões, Cinco Lentes, Cinco Testes)
- [`docs/omotenashi-checklist.md`](../omotenashi-checklist.md) — checklist operacional por tela
- [`shopman/shop/omotenashi/context.py`](../../shopman/shop/omotenashi/context.py) — OmotenashiContext (moment + audience)
- [`shopman/shop/omotenashi/copy.py`](../../shopman/shop/omotenashi/copy.py) — CopyEntry registry + resolver

---

## 1. Filosofia

O termo japonês **omotenashi** designa hospitalidade antecipatória sem expectativa de reciprocidade.
No contexto digital, isso se traduz em três princípios operacionais:

1. **Kikubari** — perceber o que a pessoa precisa antes que ela peça. Cada sinal disponível
   (hora, canal, histórico, device, estado da loja) deve alimentar uma decisão de fluxo.
2. **Ma** — o espaço intencional. Cortar é mais omotenashi que embelezar. Uma tela que respira
   comunica mais cuidado que uma tela enfeitada.
3. **Kintsugi** — quando algo quebra, consertar com ouro. A recuperação pode criar mais
   lealdade que a experiência perfeita.

**Regra estrutural:** se um sinal sobre a pessoa (aniversário, categoria preferida, status de
VIP) gera apenas copy e nenhuma decisão de fluxo, é decoração, não omotenashi. Sinal de QUEM
vira fluxo antes de virar frase.

**Regra de tom:** copy objetiva, orientada a ação. Sem floreios, sem emojis, sem melodrama.
Se dá para retirar "querido", "carinho", "juntos" e a interação continua tão cuidadosa quanto,
o omotenashi está no lugar certo (no fluxo). Se ao tirar sobra esqueleto frio, estava maquiando.

---

## 2. Sistema de Pontuação

Escala de 0 a 100, distribuída em cinco dimensões com pesos distintos. Cada dimensão pontua
de 0 ao seu peso máximo. A soma das cinco dimensões é a nota final.

| Dimensão | Peso | Foco |
|----------|------|------|
| A. Contexto Macro | 15 | Adaptação ao ambiente externo |
| B. Contexto Individual | 20 | Reconhecimento da pessoa |
| C. Antecipação | 25 | Prevenção de atrito e sugestão proativa |
| D. Recuperação | 20 | Tratamento de falhas e edge cases |
| E. Elegância | 20 | Qualidade técnica e acessibilidade |

### A. Contexto Macro (0-15 pontos)

A superfície adapta-se ao ambiente externo: tempo, canal, estado da loja, dispositivo.

| Critério | Peso | Descrição |
|----------|------|-----------|
| Momento temporal | 4 | Adapta conteúdo/comportamento ao moment (madrugada, manha, almoco, tarde, fechando, fechado). Usa `OmotenashiContext.moment`. |
| Horário de funcionamento | 3 | Mostra estado da loja (aberto, fecha em X min, fechado abre às Y). Banners de urgência quando fechando. |
| Canal | 3 | Comportamento adequado ao canal (web, WhatsApp, POS). Não replica UX de um canal em outro. |
| Estado da loja | 3 | Reage a condições operacionais: estoque crítico, happy hour, promoções ativas, pausas. |
| Device / responsividade | 2 | Mobile-first. Touch targets adequados. Layout adapta sem perda funcional. |

### B. Contexto Individual (0-20 pontos)

A superfície reconhece quem é a pessoa e adapta-se à relação.

| Critério | Peso | Descrição |
|----------|------|-----------|
| Identificação | 4 | Usa nome quando disponível. Saudação personalizada via `greeting_with_name`. |
| Estágio da relação | 4 | Diferencia anon/new/returning/VIP. Copy e fluxo variam por `audience`. |
| Momentos pessoais | 4 | Birthday banner, tier de fidelidade, marcos de relacionamento geram ação, não só frase. |
| Histórico de ações | 4 | Reorder a partir de últimos pedidos, categoria favorita, endereço/pagamento pré-preenchido. |
| Origem / contexto de entrada | 4 | Reconhece de onde veio (WhatsApp deep link, reorder, push notification) e adapta o fluxo. |

### C. Antecipação (0-25 pontos)

Dimensão mais importante. A superfície remove atrito antes que a pessoa o encontre.

| Critério | Peso | Descrição |
|----------|------|-----------|
| Pre-fill inteligente | 5 | Endereço, telefone, método de pagamento, preferência de fulfillment pré-preenchidos quando conhecidos. |
| Ordenação por relevância | 4 | Favoritos, recentes, disponíveis primeiro. Categoria favorita no topo do cardápio. |
| Alertas preventivos | 5 | Avisa ANTES do problema: fechando em breve, estoque baixo, mínimo não atingido, fora da área. Avisa na home, não no checkout. |
| Sugestão proativa | 4 | Sugere próximo passo sem ser solicitado: reorder, adicionar item, completar pedido mínimo. Uma sugestão, não cinco. |
| Eliminação de passos | 4 | Reorder com um toque. Checkout sem login quando possível. Campos opcionais como pergunta, não formulário. |
| Defaults sensatos | 3 | Toda escolha obrigatória tem default inteligente (retirada se perto, delivery se longe, PIX se recorrente). |

### D. Recuperação (0-20 pontos)

Quando algo dá errado, a superfície guia em vez de bloquear. Kintsugi digital.

| Critério | Peso | Descrição |
|----------|------|-----------|
| Erros com CTA | 4 | Todo estado de erro tem ação concreta. Nunca só "Erro" ou "Tente novamente". |
| Empty states com direção | 3 | Estados vazios guiam para ação: cardápio, primeiro pedido, cadastro de endereço. |
| Bloqueios explicados | 3 | Estado bloqueado explica POR QUE e oferece caminho alternativo. Loja fechada → horário + encomenda. |
| Alternativas de estoque | 3 | Produto indisponível sugere substitutos. "Ih, o último saiu. Que tal um destes?" |
| Falha de pagamento | 4 | PIX expirado regenera com um clique. Cartão recusado sugere outro método. Copy contextual, não sistêmica. |
| Degradação graceful | 3 | Offline, rede lenta, JS desabilitado: experiência degrada sem dead-end. WhatsApp como fallback universal. |

### E. Elegância (0-20 pontos)

A experiência é tecnicamente polida e acessível.

| Critério | Peso | Descrição |
|----------|------|-----------|
| Loading states | 3 | Skeleton, spinner ou barra de progresso em toda operação assíncrona. Nunca tela em branco. |
| Transições suaves | 2 | Sem layout shift, sem flash de conteúdo. `x-transition` em elementos dinâmicos. |
| Copy objetiva | 3 | Tom direto, orientado a ação. Sem floreio. Strings via `resolve_copy()`, não hardcoded. |
| Touch targets | 3 | Mínimo 44px em áreas de toque. Espaçamento adequado entre alvos interativos. |
| Acessibilidade | 5 | WCAG AAA contraste. Labels de screen reader. Navegação por teclado. `aria-*` em componentes dinâmicos. |
| Sem dead-ends | 2 | Toda tela tem próxima ação clara. Toda jornada termina com yoin (confirmação, tracking, reorder). |
| Ma visual | 2 | Espaço em branco intencional. Hierarquia visual clara. Sem poluição de informação. |

---

## 3. Procedimento de Auditoria

### Passo 1: Identificar superfície e audiência

Documentar:
- **Superfície**: storefront (cliente) ou backstage (operador)
- **Tela/fluxo**: nome do template ou conjunto de telas (ex: checkout flow, KDS)
- **Audiência primária**: quem usa esta superfície (cliente anon, returning, VIP; operador, cozinheiro, gerente)
- **Dispositivo primário**: mobile, desktop, tablet, totem

### Passo 2: Percorrer todos os estados

Para cada tela, verificar TODOS os estados possíveis:

| Estado | Verificação |
|--------|-------------|
| **Vazio** | Nenhum dado (carrinho vazio, histórico vazio, sem endereços). Tem direção? |
| **Loading** | Operação assíncrona em curso. Há feedback visual? |
| **Erro** | Falha de rede, validação, backend. Tem CTA? Tem alternativa? |
| **Sucesso** | Operação concluída. Há yoin? Há próximo passo? |
| **Parcial** | Dados incompletos, estoque parcial, pagamento pendente. Orientação clara? |
| **Bloqueado** | Loja fechada, fora do horário, rate limited. Explica por que? Oferece caminho? |
| **Degradado** | Sem JS, offline, rede lenta. Funciona minimamente? |

### Passo 3: Pontuar cada dimensão

Para cada dimensão (A-E), atribuir pontuação com base nos critérios detalhados na seção 2.
Anotar justificativa para cada ponto atribuído ou não atribuído.

Formato:

```
Dimensão A — Contexto Macro: 11/15
  [+4] Momento temporal: subtitle do menu varia por moment via omotenashi copy
  [+3] Horário: shop_hint mostra "Aberto até 19h" / "Últimos pedidos"
  [+1] Canal: layout adequado mas sem adaptação real de fluxo por canal
  [+3] Estado da loja: banner de urgência funciona, happy hour refletido
  [+0] Device: touch targets abaixo de 44px nos botões de quantidade
```

### Passo 4: Calcular total

Somar as cinco dimensões. O total é a nota da superfície.

### Passo 5: Catalogar findings

Para cada problema identificado, registrar:

| Campo | Descrição |
|-------|-----------|
| **ID** | Identificador sequencial (ex: F-01, F-02) |
| **Dimensão** | A, B, C, D ou E |
| **Severidade** | P0 (bloqueante), P1 (grave), P2 (moderada), P3 (polish) |
| **Tela** | Template ou componente afetado |
| **Estado** | Em que estado o problema ocorre (vazio, erro, loading, etc.) |
| **Descrição** | O que está errado, observável, sem adjetivos |
| **Impacto** | O que a pessoa experimenta por causa do problema |
| **Recomendação** | Ação concreta para corrigir, com referência a código/template quando possível |

### Passo 6: Definir plano de remediação

Agrupar findings por severidade. Priorizar P0 antes de qualquer release.
P1 no próximo WP. P2/P3 no backlog com prazo estimado.

---

## 4. Limiares Mínimos

| Faixa | Classificação | Ação |
|-------|---------------|------|
| **0-49** | BLOQUEADO | Não pode ir a produção. Remediação obrigatória antes de release. |
| **50-69** | ALERTA | Pode ir a produção com plano de remediação documentado e prazo para P1+. |
| **70-84** | BOM | Items de polish (P2/P3). Superfície funcional e cuidadosa. |
| **85-100** | EXCELENTE | Omotenashi realizado. Kaizen contínuo nos detalhes. |

### Limiares por dimensão

Além da nota total, cada dimensão tem limiar mínimo individual. Se qualquer dimensão
ficar abaixo de 40% do seu peso máximo, é bloqueante independente da nota total.

| Dimensão | Peso | Limiar mínimo (40%) |
|----------|------|---------------------|
| A. Contexto Macro | 15 | 6 |
| B. Contexto Individual | 20 | 8 |
| C. Antecipação | 25 | 10 |
| D. Recuperação | 20 | 8 |
| E. Elegância | 20 | 8 |

---

## 5. Checklists por Dimensão

### A. Contexto Macro — Checklist

- [ ] A saudação (`greeting`) varia por hora do dia (Bom dia / Boa tarde / Boa noite)
- [ ] O `moment` é computado corretamente (madrugada/manha/almoco/tarde/fechando/fechado)
- [ ] Copy contextual varia por moment onde relevante (MENU_SUBTITLE, CART_EMPTY, etc.)
- [ ] Estado da loja visível na superfície (aberto, fecha em X, fechado abre às Y)
- [ ] Banner de urgência aparece quando `moment == fechando`
- [ ] Loja fechada: a pessoa pode navegar mas sabe que não pode pedir agora
- [ ] Layout funciona corretamente em viewport de 375px (mobile-first)
- [ ] Touch targets >= 44px em todos os elementos interativos
- [ ] Sem scroll horizontal em nenhum viewport
- [ ] Canal refletido no comportamento (ex: WhatsApp não mostra carrinho persistente)
- [ ] Happy hour / promoções ativas refletidos na UI quando relevante
- [ ] Horários de operação acessíveis sem navegação extra

### B. Contexto Individual — Checklist

- [ ] Nome do cliente aparece quando autenticado (`customer_name`)
- [ ] Saudação personalizada (`greeting_with_name`) no ponto de entrada
- [ ] Audiência (`audience`) é computada corretamente (anon/new/returning/VIP)
- [ ] Copy varia por audience onde configurado (CART_EMPTY, PAYMENT_CONFIRMED, etc.)
- [ ] Birthday banner aparece no dia do aniversário (`is_birthday`)
- [ ] Aniversário gera ação de fluxo (promoção, brinde), não só banner decorativo
- [ ] Categoria favorita (`favorite_category`) influencia ordenação do cardápio
- [ ] Últimos pedidos acessíveis para reorder (returning/VIP)
- [ ] Endereço padrão pré-selecionado no checkout quando disponível
- [ ] Método de pagamento recente sugerido primeiro
- [ ] Informações de fidelidade (stamps, tier) visíveis para clientes com programa ativo
- [ ] Fluxo de primeiro acesso (AUDIENCE_NEW) é guiado sem condescendência

### C. Antecipação — Checklist

- [ ] Telefone/contato pré-preenchido se já conhecido
- [ ] Endereço de entrega pré-preenchido se `is_default` existe
- [ ] Fulfillment preference pré-selecionada com base em histórico
- [ ] Produtos favoritos/recentes aparecem antes dos demais no cardápio
- [ ] Produtos indisponíveis aparecem por último ou com badge, não somem
- [ ] Aviso de "fechamos em breve" aparece ANTES do checkout, não durante
- [ ] Aviso de mínimo de pedido aparece no carrinho, não no checkout
- [ ] Aviso de "fora da área" aparece na home/carrinho, não no checkout
- [ ] Sugestão de reorder aparece para returning/VIP com histórico
- [ ] Campos opcionais (cupom, notas) são pergunta que revela input, não formulário aberto
- [ ] Checkout pula steps já resolvidos (contato verificado, endereço default)
- [ ] Próximo passo sugerido em toda tela terminal (confirmação → tracking, tracking → reorder)

### D. Recuperação — Checklist

- [ ] Carrinho vazio tem CTA direcionando ao cardápio (não só "vazio")
- [ ] Histórico vazio direciona para primeiro pedido
- [ ] Endereço vazio direciona para cadastro
- [ ] Produto indisponível sugere substitutos quando disponíveis
- [ ] CEP não encontrado oferece digitação manual do endereço
- [ ] PIX expirado regenera com um clique, sem recomeçar checkout
- [ ] Cartão recusado sugere outro método de pagamento
- [ ] Cancelamento recusado explica motivo e oferece WhatsApp
- [ ] Rate limit mostra countdown e oferece WhatsApp como alternativa
- [ ] Erro de rede tem retry automático ou manual sem perda de estado
- [ ] Loja fechada mostra horário de abertura e permite encomenda quando possível
- [ ] Nenhuma tela de erro é dead-end (sempre há próxima ação)

### E. Elegância — Checklist

- [ ] Toda operação HTMX tem indicador de loading (hx-indicator ou Alpine state)
- [ ] Skeleton/spinner em toda requisição assíncrona visível ao usuário
- [ ] `x-transition` em todo elemento que aparece/desaparece via Alpine
- [ ] Sem flash de conteúdo não-estilizado (FOUC) no carregamento inicial
- [ ] Sem layout shift quando conteúdo dinâmico carrega
- [ ] Toda string de interface usa `resolve_copy()` ou `{% omotenashi_copy %}`, não hardcoded
- [ ] Copy é objetiva: verbos de ação, sem adjetivos supérfluos, sem emojis
- [ ] Contraste WCAG AAA (7:1) em texto principal, AA (4.5:1) em texto secundário
- [ ] Labels `aria-label` / `aria-describedby` em inputs, botões, e componentes dinâmicos
- [ ] Navegação por teclado funcional: Tab order, Enter/Space em botões, Escape fecha modais
- [ ] Touch targets >= 44x44px, com espaçamento >= 8px entre alvos adjacentes
- [ ] Hierarquia visual clara: títulos > subtítulos > corpo > metadados

---

## 6. Adições para Superfícies de Operador (Backstage)

Superfícies de operador (KDS, POS, fila de pedidos, produção, fechamento) têm requisitos
adicionais que refletem o contexto de trabalho: velocidade, multitarefa, ambiente ruidoso,
atenção dividida.

### Velocidade

- [ ] Resposta percebida < 200ms para ações primárias (confirmar, avançar, marcar pronto)
- [ ] HTMX swaps com `hx-swap="innerHTML"` ou `outerHTML` sem full page reload
- [ ] Ações de um toque: confirmar pedido, avançar status, marcar item pronto
- [ ] Sem modais desnecessários em fluxo primário (modal só para ações destrutivas)
- [ ] Shortcuts de teclado para ações frequentes quando em desktop

### Escaneabilidade

- [ ] Informação crítica (status, ETA, itens) visível sem scroll no viewport primário
- [ ] Hierarquia por cor/tamanho: urgente > normal > baixa prioridade
- [ ] Números grandes e legíveis a 1m de distância (KDS em tela grande)
- [ ] Sem abas que escondem informação operacionalmente crítica
- [ ] Contadores visíveis: pedidos pendentes, tempo médio, alertas ativos

### Feedback Sensorial

- [ ] Som/vibração para novo pedido (configurável, desligável)
- [ ] Alerta sonoro para pedido próximo do SLA (tempo de espera)
- [ ] Feedback visual imediato para ação (cor muda, elemento move, check aparece)
- [ ] Alerta visual persistente para condições críticas (estoque zerado, equipamento parado)

### Proteção contra Erro

- [ ] Ações destrutivas (cancelar pedido, void work order) pedem confirmação
- [ ] Undo disponível para ações reversíveis (marcar pronto → desmarcar)
- [ ] Confirmação mostra resumo do que vai acontecer, não só "tem certeza?"
- [ ] Ações acidentais (toque duplo) são ignoradas via debounce
- [ ] Estado do pedido é visível antes e depois da ação (feedback de transição)

### Contexto Operacional

- [ ] Alergias e restrições alimentares em destaque nos itens do pedido
- [ ] Observações do cliente visíveis sem ação extra
- [ ] Priorização visual de pedidos (por tempo de espera, não só por ordem)
- [ ] Indicador de tipo de fulfillment (retirada vs entrega) sem ambiguidade
- [ ] Fechamento de turno com resumo operacional (pedidos, tempo médio, avaliações)

### Multitarefa

- [ ] Tela não exige atenção contínua (updates via SSE/polling, não ação do operador)
- [ ] Estado persiste se operador navega e volta (não perde contexto)
- [ ] Informação de múltiplos pedidos simultâneos sem sobreposição visual
- [ ] Modo de alerta passivo: informação nova chega ao operador, não o contrário

---

## 7. Classificação de Severidade (Findings)

| Severidade | Definição | Prazo | Exemplo |
|------------|-----------|-------|---------|
| **P0** | Dead-end, perda de dados, ou bloqueio de jornada principal | Antes do release | Checkout falha sem mensagem de erro. Pagamento perde estado ao recarregar. |
| **P1** | Experiência significativamente degradada para segmento relevante | Próximo WP | Empty state sem CTA. Erro de pagamento sem alternativa. Kintsugi ausente em fluxo de cancelamento. |
| **P2** | Atrito perceptível mas contornável | Backlog com prazo | Touch target de 36px em botão secundário. Copy hardcoded em vez de omotenashi. Loading state ausente em operação rápida. |
| **P3** | Polish e refinamento | Backlog sem prazo | Transição ausente em toggle. Contraste AA em vez de AAA em texto terciário. Ma insuficiente entre seções. |

---

## 8. Exemplo de Auditoria

### Superfície: Checkout (storefront, cliente, mobile)

**Data:** 2026-04-22
**Auditor:** [nome]
**Versão:** post-WP-OMO-5

---

#### Pontuação

**A. Contexto Macro: 12/15**

| Critério | Pts | Justificativa |
|----------|-----|---------------|
| Momento temporal | 4/4 | Checkout não varia por moment (correto — foco é finalizar) |
| Horário | 2/3 | Sem banner de urgência "fechamos em X min" dentro do checkout |
| Canal | 3/3 | Checkout web funciona adequadamente; POS tem fluxo próprio |
| Estado da loja | 2/3 | Não bloqueia checkout se loja fecha durante o processo |
| Device | 1/2 | Touch target do stepper de quantidade abaixo de 44px |

**B. Contexto Individual: 17/20**

| Critério | Pts | Justificativa |
|----------|-----|---------------|
| Identificação | 4/4 | Nome do cliente no resumo do pedido |
| Estágio da relação | 4/4 | Step de contato pulado para returning (já verificado) |
| Momentos pessoais | 3/4 | Birthday banner na home mas sem ação no checkout (desconto, brinde) |
| Histórico | 4/4 | Endereço default pré-selecionado, método de pagamento sugerido |
| Origem | 2/4 | Não adapta flow se veio de reorder vs navegação normal |

**C. Antecipação: 22/25**

| Critério | Pts | Justificativa |
|----------|-----|---------------|
| Pre-fill | 5/5 | Telefone, endereço, fulfillment pré-preenchidos |
| Ordenação | 4/4 | Slots de retirada ordenados por proximidade temporal |
| Alertas preventivos | 4/5 | Mínimo de pedido no carrinho; falta alerta de "última unidade" |
| Sugestão proativa | 4/4 | Upsell discreto no carrinho, complemento sugerido |
| Eliminação de passos | 3/4 | Contato verificado pula step; notas/cupom como pergunta |
| Defaults | 2/3 | Retirada como default quando perto; falta default de horário |

**D. Recuperação: 16/20**

| Critério | Pts | Justificativa |
|----------|-----|---------------|
| Erros com CTA | 3/4 | Validação inline funciona; erro de backend genérico em edge case |
| Empty states | 3/3 | Checkout não tem empty state relevante |
| Bloqueios explicados | 3/3 | Loja fechada redirecionada antes de chegar aqui |
| Alternativas de estoque | 2/3 | Banners de indisponibilidade no carrinho; sem sugestão inline |
| Falha de pagamento | 3/4 | PIX regenera; cartão recusado ainda com mensagem sistêmica |
| Degradação | 2/3 | Form funciona sem JS mas perde steps; sem fallback offline |

**E. Elegância: 16/20**

| Critério | Pts | Justificativa |
|----------|-----|---------------|
| Loading states | 3/3 | Spinner no submit, skeleton nos slots |
| Transições | 2/2 | x-transition nos steps, sem layout shift |
| Copy | 2/3 | Maioria via omotenashi copy; 2 strings hardcoded encontradas |
| Touch targets | 2/3 | Maioria OK; stepper qty abaixo do mínimo |
| Acessibilidade | 4/5 | Contraste AAA; falta aria-live em região de atualização dinâmica |
| Sem dead-ends | 2/2 | Confirmação → tracking sempre disponível |
| Ma visual | 1/2 | Steps bem espaçados; resumo lateral denso no mobile |

---

#### Total: 83/100 — BOM

#### Findings

| ID | Dim | Sev | Tela | Estado | Descrição | Recomendação |
|----|-----|-----|------|--------|-----------|--------------|
| F-01 | E | P2 | checkout step qty | Normal | Touch target do stepper de quantidade é 36x36px | Aumentar para 44x44px mínimo |
| F-02 | A | P2 | checkout | Fechando | Sem indicação de urgência se loja fecha em < 30min | Adicionar banner contextual via `MOMENT_FECHANDO` |
| F-03 | B | P3 | checkout | Birthday | Aniversário detectado mas sem ação no checkout | Aplicar desconto/brinde automaticamente quando promoção de birthday ativa |
| F-04 | D | P2 | payment | Card refused | Mensagem de cartão recusado usa texto sistêmico do gateway | Mapear erros do gateway para copy omotenashi via `KINTSUGI_CARD_REFUSED` |
| F-05 | E | P3 | checkout summary | Normal | Resumo lateral denso no mobile, sem ma suficiente | Colapsar detalhes com `<details>` no mobile, expandir no desktop |
| F-06 | E | P2 | checkout slots | Dinâmico | Região de slots atualiza sem `aria-live` | Adicionar `aria-live="polite"` no container de slots |
| F-07 | C | P3 | checkout horário | Normal | Sem default de horário de retirada (primeiro slot disponível) | Pré-selecionar próximo slot disponível |

---

#### Plano de Remediação

| Severidade | Findings | Ação |
|------------|----------|------|
| P0 | — | Nenhum bloqueante |
| P1 | — | Nenhum grave |
| P2 | F-01, F-02, F-04, F-06 | Próximo WP |
| P3 | F-03, F-05, F-07 | Backlog |

---

## 9. Template de Auditoria

Use este template para novas auditorias. Copiar e preencher.

```markdown
# Auditoria Omotenashi — [Nome da Superfície]

**Data:** YYYY-MM-DD
**Auditor:** [nome]
**Superfície:** storefront | backstage
**Tela/Fluxo:** [nome do template ou fluxo]
**Audiência:** [cliente anon | returning | VIP | operador | gerente]
**Device primário:** [mobile | desktop | tablet | totem]

## Pontuação

### A. Contexto Macro: __/15
| Critério | Pts | Justificativa |
|----------|-----|---------------|
| Momento temporal | /4 | |
| Horário | /3 | |
| Canal | /3 | |
| Estado da loja | /3 | |
| Device | /2 | |

### B. Contexto Individual: __/20
| Critério | Pts | Justificativa |
|----------|-----|---------------|
| Identificação | /4 | |
| Estágio da relação | /4 | |
| Momentos pessoais | /4 | |
| Histórico | /4 | |
| Origem | /4 | |

### C. Antecipação: __/25
| Critério | Pts | Justificativa |
|----------|-----|---------------|
| Pre-fill | /5 | |
| Ordenação | /4 | |
| Alertas preventivos | /5 | |
| Sugestão proativa | /4 | |
| Eliminação de passos | /4 | |
| Defaults | /3 | |

### D. Recuperação: __/20
| Critério | Pts | Justificativa |
|----------|-----|---------------|
| Erros com CTA | /4 | |
| Empty states | /3 | |
| Bloqueios explicados | /3 | |
| Alternativas de estoque | /3 | |
| Falha de pagamento | /4 | |
| Degradação | /3 | |

### E. Elegância: __/20
| Critério | Pts | Justificativa |
|----------|-----|---------------|
| Loading states | /3 | |
| Transições | /2 | |
| Copy | /3 | |
| Touch targets | /3 | |
| Acessibilidade | /5 | |
| Sem dead-ends | /2 | |
| Ma visual | /2 | |

## Total: __/100 — [BLOQUEADO | ALERTA | BOM | EXCELENTE]

## Findings

| ID | Dim | Sev | Tela | Estado | Descrição | Recomendação |
|----|-----|-----|------|--------|-----------|--------------|
| F-01 | | | | | | |

## Plano de Remediação

| Severidade | Findings | Ação |
|------------|----------|------|
| P0 | | |
| P1 | | |
| P2 | | |
| P3 | | |
```

---

*Omotenashi Audit Framework — Django Shopman, 2026.*
*Hospitalidade é estrutura e timing, não palavras bonitas.*
