# Auditoria de Excelência — Shopman App vs Core

Você é um auditor sênior avaliando se o `shopman-app` explora o `shopman-core` de forma plena e elegante — e se o conjunto atinge nível de excelência comparável a Toast, Square, Shopify, iFood, Take.app.

**Escopo**: tudo testável/observável em dev local. Deploy está FORA.
**Output**: `AUDIT-REPORT.md` na raiz do repo, formato abaixo. Leia o código real, não confie em docs.

---

## 12 Verificações

### 1. CORE SUBUTILIZADO
Leia TODOS os models/services/APIs do Core. Para cada capacidade NÃO importada pelo App, verificar módulo a módulo:
- **offering**: ProductComponent (BOM vendável), Bundle, import/export — usados?
- **stocking**: StockPlanning, reorder_point, StockAlert automation completa — usados?
- **crafting**: WorkOrder lifecycle completo, BOM explosion — App usa tudo?
- **ordering**: Session.handle_type/handle_ref — App explora ou ignora?
- **customers**: Customer merge, consent, tags, groups, RFM scoring — usados?
- **auth**: Device trust, rate limiting por IP, lockout — ativados?
- **payments**: Refund parcial, multi-payment, split payment — suportados?
- **utils**: Quais utils o App importa? Quais ignora?

Para cada: é lacuna real ou decisão consciente? Consultar CLAUDE.md, ROADMAP.md.

### 2. HANDLERS & PIPELINE
Para CADA handler em `setup.py`: trata todos os erros? É idempotente (2x = mesmo resultado)? Loga adequadamente (INFO sucesso, WARNING skip, ERROR falha)? Atualiza directive.status sempre (nunca fica "pending" eternamente)? Timeout handlers verificam condição antes de agir? Há race conditions (payment webhook + cancel simultâneo em TODOS os payment handlers)? Dependências circulares (handler A → directive → handler B → directive → handler A)?

### 3. TRANSIÇÕES DE STATUS
Mapear TODAS as transições de Order.status. Para cada uma: quem executa, tem guard, emite evento, dispara signal, roda pipeline, envia notificação? Procurar transições faltantes ou inconsistentes (ex: DISPATCHED→CANCELLED é possível? Deveria ser? RETURNED pode voltar a COMPLETED? Quem garante que terminal_statuses não transitam?).

### 4. FLUXO FINANCEIRO
Rastrear dinheiro end-to-end: `unit_price_q` → `line_total_q` → `Order.total_q` → `payment.amount_q`. Valores SEMPRE batem? Descontos (coupon, D-1, happy hour, employee) aplicados onde exatamente? Total reflete descontos ou é bruto? Refund parcial funciona E2E (ReturnService → PaymentRefundHandler → backend)? Se refund falha no gateway, o que acontece — retry, alerta, inconsistência? `monetary_mult` é usado consistentemente ou tem `int(qty * price)` espalhado? Algum lugar usa float/Decimal para centavos em vez de int?

### 5. NOTIFICAÇÕES
Para cada template (14 listados em data-schemas.md): existe em todos os backends (email, manychat, whatsapp, sms, console)? Fallback chain funciona (manychat falha → sms → email → console)? `_build_context()` monta contexto completo para TODOS os templates? `_resolve_recipient()` encontra destinatário em TODOS os cenários (web, whatsapp, POS, iFood)? Template degrada sem quebrar se variável ausente? Falha de notificação é logada/alertada ou silenciosa?

### 6. UX / TEMPLATES
Avaliar storefront contra benchmarks:
- **Acessibilidade**: inputs com labels? aria-labels em botões? alt em imagens? Focus visible?
- **Mobile**: touch targets ≥44px? `inputmode` correto (tel p/ telefone, numeric p/ CEP, email p/ email)?
- **Loading**: toda ação HTMX tem indicador visual? Botões desabilitam durante submit? Double-submit prevenido?
- **Erros**: toda chamada HTMX tem `hx-on::response-error`? Validação inline? Erro de rede com mensagem amigável?
- **Empty states**: carrinho vazio, pedidos vazios, histórico vazio — mensagem + CTA ou tela em branco?
- **Convenção**: NENHUM template usa `onclick`, `onchange`, `document.getElementById`, `classList.toggle` (proibidos por CLAUDE.md)?

### 7. ADMIN / OPERADOR
Operador faz TUDO sem shell? CRUD completo com campos readonly adequados? Ações em massa (cancelar pedidos, reprocessar directives falhados, reenviar notificação, exportar)? Dashboard KPIs corretos e queries eficientes (sem N+1)? Filtros/busca em pedidos (status, data, canal, cliente), produtos (nome, SKU), directives (status, topic)? Gestor de pedidos cobre TODOS os status com ações (avançar, rejeitar, notas, histórico)?

### 8. SEGURANÇA ANTI-FALHAS
- **Atomicidade**: operações multi-escrita usam `transaction.atomic`? Estado inconsistente se falha no meio?
- **Concorrência**: `select_for_update` nos lugares certos? Race condition de 2 tabs no mesmo carrinho?
- **Validação**: todos os forms validam server-side? Phone normalization consistente? Monetários positivos?
- **Sessão**: session key unpredictable? Access tokens expiram? Rate limiting em login/OTP?
- **Idempotência**: webhooks (PIX, Stripe) são idempotentes? Refresh na página de pagamento causa problema?

### 9. OBSERVABILIDADE
Handlers logam com contexto suficiente (order_ref, directive_id, handler, duração)? Directives falhados fáceis de diagnosticar (last_error preenchido)? Retry de directives é automático ou manual? Events do Order cobrem TODAS as ações (audit trail — consigo reconstruir história completa de um pedido)? Analytics views cobrem necessidades operacionais?

### 10. SEED & TESTABILIDADE
`make seed` cria cenário realista? Inclui pedidos em diferentes fases, clientes com histórico, estoque variado? Quais fluxos têm teste E2E e quais NÃO? Happy + sad path cobertos para checkout, payment, cancel, return? Testes de integração realmente integram (não mockam tudo)?

### 11. CONSISTÊNCIA ARQUITETURAL
Handlers seguem mesmo padrão (payload → validation → logic → state → status)? Views seguem mesmo padrão (permission → fetch → context → render)? Alguma view faz lógica de negócio que deveria ser handler/service? Backends implementam protocolos (protocols.py)? Erros tratados consistentemente? Algum handler/view é outlier (muito grande, acoplado)?

### 12. ELEGÂNCIA & SIMPLICIDADE
Dead code (imports, funções, views sem template, routes sem view). Duplicação (checkout + API + POS fazendo o mesmo de formas diferentes — helpers faltantes?). Complexidade (funções >100 linhas, ifs 3+ níveis, módulos >500 linhas). Naming (ref vs code por CLAUDE.md, variáveis genéricas). Over-engineering (abstrações sem uso, configurabilidade inútil). Under-engineering (hardcoded values, magic strings repetidas, constantes que deveriam ser centralizadas).

---

## Formato do Relatório

```markdown
# Audit Report — Shopman Excellence Review
**Data**: {data}  |  **Escopo**: dev-local (excl. deploy)

## Resumo Executivo
- 🔴 Críticos: X  |  🟠 Importantes: X  |  🟡 Menores: X  |  💡 Sugestões: X  |  ✅ Destaques: X

## Achados (por categoria, 1-12)
Para cada: descrição, evidência (arquivo:linha), impacto, sugestão.

## Core Não Utilizado
| Módulo | Capacidade | Avaliação |

## Comparação com Benchmarks
| Aspecto | Shopman | Toast/Shopify/iFood | Gap? |

## Veredicto
Parágrafo honesto: onde é excelente, onde precisa melhorar, o que separa de primeira linha.
```

## Regras
- Ler código real, citar arquivo:linha.
- Priorizar impacto no usuário final (lojista artesão + cliente).
- Não propor mudanças no Core.
- Consultar CLAUDE.md, PRODUCTION-PLAN.md, EVOLUTION-PLAN.md, docs/ antes de reportar gaps.
- Benchmark realista: negócios artesanais PME, não enterprise.
