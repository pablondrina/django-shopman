# Webhooks — códigos de status na falha de autenticação

> Estado atual + decisão pendente sobre padronização. **Decisão de contrato do Pablo**, não bug.

## Estado atual (verificado 2026-06-30)

Cada webhook é um contrato próprio com o gateway. Hoje os códigos divergem na rejeição
por token ausente/inválido:

| Webhook | Arquivo | Falha de auth | Modelo |
|---|---|---|---|
| Efí (PIX) | [efi.py:73](../../shopman/shop/webhooks/efi.py) | **401 Unauthorized** | token compartilhado |
| iFood | [ifood.py:70](../../shopman/shop/webhooks/ifood.py) | **403 Forbidden** | token compartilhado |
| Stripe (cartão) | [stripe.py](../../shopman/shop/webhooks/stripe.py) | **400 Bad Request** | assinatura HMAC |

O Stripe é legitimamente diferente: rejeita por **falha de assinatura HMAC** (não há
"token" a autenticar), e 400 é o correto para corpo/assinatura inválidos. A divergência
real é **Efí 401 vs iFood 403** para o mesmo caso (token de webhook errado).

## Por que existe

`ifood.py` foi especificado com 403 explícito (WP-GAP-01); `efi.py` preexistia com 401.
Como cada webhook é um endpoint que só o gateway dele chama, a divergência **não é
visível externamente** — cada gateway recebe o código que seu próprio contrato espera.
Internamente, porém, é inconsistente.

## Recomendação (para o Pablo decidir)

Padronizar os webhooks **de token** em **401 Unauthorized** (mantendo o 400 do Stripe por
ser HMAC):

- **401** é semanticamente correto: "a autenticação falhou — credencial ausente/inválida".
- **403** significa "autenticado, mas sem permissão" — ambíguo para um webhook (não há
  identidade autenticada cujo acesso seja negado).

A troca seria mudar [ifood.py:70](../../shopman/shop/webhooks/ifood.py) de
`HTTP_403_FORBIDDEN` para `HTTP_401_UNAUTHORIZED` (+ ajustar o teste e o docstring).

⚠️ **Não alterar sem confirmar** se o painel/expectativa do iFood depende do 403. É escolha
de contrato com o gateway, não de código. Se confirmado que o iFood não se importa, abrir
um ADR curto e padronizar.
