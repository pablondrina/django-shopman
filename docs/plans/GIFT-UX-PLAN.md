# GIFT-UX-PLAN — Pedido como presente (entrega para terceiro) — spec canônica

> **Fonte única da verdade para presente/entrega-a-terceiro no storefront.**
> Ler antes de tocar qualquer tela onde o cliente possa estar comprando para
> outra pessoa. Não reinventar, não resumir. Desenho aprovado por Pablo em
> 2026-06-13 (refinamentos incorporados).
>
> **Status (2026-06-14): slice backend do MVP ENTREGUE** (commit `f0fbf696`).
> Pronto: integridade pura (`intents.gift.build_gift_data`), wiring nas duas
> superfícies (API CheckoutView/Nuxt + interpret_checkout/HTML), propagação
> Session→Order (`is_gift`/`recipient`/`gift_message` na whitelist de ops + Op
> Serializer allowlist + lista do CommitService), serializer, data-schemas, e
> testes (unitário + contrato). **Falta (precisa conferência visual):** UX no
> checkout (pergunta única "É para presente?" + campos do destinatário +
> AddressPicker sem pré-selecionar salvos + ocultar valores), KDS mostrando o
> destinatário, e a notificação (comprador notificado; destinatário sem spoiler).

## Princípio

Comprar presente é comum e hoje o checkout **colapsa três papéis em um só**
(comprador = destinatário = dono do endereço). Presente desacopla o
destinatário e o endereço do comprador — **sem** tocar a identidade nem a
cobrança, que continuam do comprador autenticado.

## Os três papéis

1. **Comprador/pagador** — quem está logado. Identidade verificada (doorman/OTP)
   + cobrança. Já existe (`Session.data["customer"]` = `{name, phone, ref, ...}`).
   **Não muda.** PIX/cartão sempre no nome dele.
2. **Destinatário** — nome + contato de quem recebe. Pode não ser cliente.
3. **Endereço de entrega** — o do destinatário.

## Decisão central: **não criar usuário para o destinatário**

Pelos princípios do projeto, cadastrar conta para o presenteado é errado:

- **Doorman é posse-do-telefone.** Conta nasce de alguém verificar o próprio
  número via OTP. Criar conta para terceiro não verificado produz identidade
  sem dono — fura o modelo de auth.
- **LGPD/privacidade.** Cadastrar terceiro sem consentimento dele.
- **Colisão.** Se o telefone do destinatário já é de um cliente, mexeria na
  conta de outra pessoa.
- **Omotenashi.** Ninguém pediu uma conta.

→ **Destinatário é dado contextual do pedido, não identidade.** Ele só vira
`Customer` se/quando ele mesmo autenticar, no tempo dele.

## Onde os dados vivem (Core é sagrado)

Sem migração, sem tocar `packages/` estrutural — JSONField, como o projeto manda:

- `Order.data["recipient"] = {name, phone}` — espelha a forma do `customer`,
  mas é o presenteado. Só presente quando é presente.
- `Order.data["is_gift"] = true`.
- `Order.data["gift_message"]` — mensagem para o destinatário. **Separada** de
  `order_notes` (que é operacional/cozinha).
- Endereço do destinatário já cabe em `delivery_address_structured` — **zero
  campo novo**. O `AddressPicker` já trata "endereço de terceiro" como "novo
  endereço".
- Propagar `recipient`/`is_gift`/`gift_message` pela lista explícita do
  `CommitService` (regra 5 do CLAUDE.md) e **registrar em
  `docs/reference/data-schemas.md` ANTES de usar** (regra 3).

### Requisito de integridade (Pablo frisou)

O JSON precisa ser **sempre preenchido de forma correta e completa**: quando
`is_gift=true`, `recipient.name` e `recipient.phone` são obrigatórios e
validados no serializer; `gift_message` é opcional mas, se vier, persistido
íntegro; nunca gravar `recipient` parcial. Quando `is_gift=false`, as três
chaves não existem (não gravar vazias). Cobrir com teste de contrato.

## UX no checkout (omotenashi-first)

**Pergunta única — não dupla** (decisão do Pablo): no mundo real, sem dizer
nada, é para a própria pessoa. Então a única pergunta é **"É para presente?"**
(toggle/checkbox discreto), default desligado. Nada de "Para mim / Para outra
pessoa".

Ao ligar "É para presente?":
- nome + telefone **do destinatário** (campos próprios; **não** sobrescrevem o
  contato do comprador);
- endereço via `AddressPicker` (sem pré-selecionar os salvos do comprador);
- mensagem do presente (opcional);
- opção "ocultar valores" na nota/recibo (presente não mostra preço).

Faz sentido pleno **com entrega**. Em **retirada**, presente vira só embalagem
+ mensagem (o comprador leva) — decisão de produto: provavelmente esconder o
toggle quando `fulfillment_type == "pickup"`, ou degradar para "embalar para
presente". Confirmar antes de implementar.

## Notificações

**O comprador é quem é notificado** (decisão do Pablo) — ele pediu, tem a
conta, acompanha o pedido. O destinatário, no máximo, um aviso de chegada
("seu pedido está a caminho") **sem estragar a surpresa nem vazar que é
presente**. Decisão de canal a detalhar quando implementar.

## Operador / KDS

Precisa ver, destacado: **"Presente · entregar para [destinatário] ·
[telefone do destinatário]"** — para o entregador contatar quem recebe, não o
comprador. Vincula com a superfície de operador (ver KDS/expedição).

## MVP vs. evolução

- **MVP**: papéis 2+3 como dado contextual + pergunta única "É para presente?"
  + `AddressPicker` reutilizado + `gift_message` + KDS mostrando o
  destinatário + comprador notificado. Resolve ~90% sem tocar o Core
  estrutural.
- **Evolução** (features próprias): agenda de destinatários do comprador
  (Guestman como CRM dele — presentear de novo em 1 toque); destinatário
  reivindica a conta depois (ele autentica no tempo dele); endereço incompleto
  do destinatário resolvido por link para ele confirmar o próprio endereço sem
  expor o pedido.

## Regras invariantes

- **Nunca** criar `Customer`/conta para o destinatário no ato do pedido.
- **Nunca** sobrescrever o contato do comprador com o do destinatário.
- **Nunca** gravar `recipient` parcial; `is_gift=true` exige nome + telefone.
- **Nunca** expor que é presente para o destinatário numa notificação de
  surpresa.
- Cobrança é **sempre** do comprador autenticado.
- Endereço do destinatário reusa `delivery_address_structured` + o
  `AddressPicker` — zero duplicação, lat/lng/place_id sempre persistidos.
