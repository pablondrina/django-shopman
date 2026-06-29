# Runbook — Ativar Focus NFe (NFC-e): homologação → produção

> Passo-a-passo objetivo para ligar a emissão de NFC-e via Focus NFe. A "parte de regra"
> (CFOP 5102/5405, CSOSN 102/500, PIS-COFINS 99) já está aplicada e validada pelo contador
> — ver [fiscal-parametrizacao-nfce](../reference/fiscal-parametrizacao-nfce.md). Este runbook
> cobre só **conta + credenciais + ligar no ambiente**.

## Bucket 1 — Lado Focus NFe + SEFAZ (Pablo + contador)

Pré-requisitos que vivem **no painel da Focus / na SEFAZ**, não no nosso env:

1. **Reativar a conta Focus NFe.**
2. **Certificado digital A1 (eCNPJ)** — *só A1* (A3 não serve: servidores em nuvem). Upload no painel da Focus.
3. **Cadastrar a empresa** no painel: CNPJ, **Inscrição Estadual** ativa, regime = Simples Nacional
   (casa com os CSOSN 102/500 definidos pelo contador).
4. **CSC + ID do CSC** (SEFAZ-PR) — contador solicita online; cadastrar token+ID no painel Focus.
   É o que gera o **QR Code** da NFC-e (sem ele a nota sai, mas o consumidor não valida o QR).
5. **Tokens da API** no painel Focus: um de **homologação** (staging) e um de **produção** (alpha).

## Bucket 2 — Ligar no ambiente (engenharia)

O **CNPJ emitente** vem automaticamente da config da loja (`Shop.document`, Admin → config da loja).
Só sobrescrever via `FOCUS_NFE_CNPJ_EMITENTE` se o emitente for diferente do CNPJ da loja.

### Staging (homologação)
No DigitalOcean → Apps → `shopman-staging` → Settings → App-Level Environment Variables (Encrypt nos segredos):
```
SHOPMAN_FISCAL_ADAPTER=shopman.shop.adapters.fiscal_focusnfe.FocusNFeBackend
FOCUS_NFE_TOKEN=<token de homologação>     (Encrypt)
FOCUS_NFE_ENVIRONMENT=homologacao
# FOCUS_NFE_CNPJ_EMITENTE=                  # só se diferente de Shop.document
```
Redeploy → emitir uma **NFC-e de teste** (sem validade fiscal) para validar ponta-a-ponta.

### Produção (alpha)
Mesmas chaves, trocando:
```
FOCUS_NFE_TOKEN=<token de produção>         (Encrypt)
FOCUS_NFE_ENVIRONMENT=producao
```
⚠️ Token de produção é **diferente** do de homologação. Não receber dinheiro real sem a NFC-e
saindo (gate de prontidão do alpha — ver [GO-LIVE-CREDENTIALS-MATRIX](../plans/GO-LIVE-CREDENTIALS-MATRIX.md) §3).

## Verificação

O gate `manage.py check --deploy` e `integration_readiness.focus_nfe_readiness` exigem:
adapter apontado + `FOCUS_NFE_TOKEN` + CNPJ emitente (config ou `Shop.document`), e barram
`producao` em staging / `homologacao` em produção (segurança de ambiente).

## Referências
- [GO-LIVE-CREDENTIALS-MATRIX](../plans/GO-LIVE-CREDENTIALS-MATRIX.md) — matriz por fase + gate do alpha
- [fiscal-parametrizacao-nfce](../reference/fiscal-parametrizacao-nfce.md) — CFOP/CSOSN/PIS-COFINS (contador)
- [Focus NFe — CSC](https://focusnfe.com.br/blog/o-que-e-token-csc/) · [A1 vs A3](https://focusnfe.com.br/blog/nfe-saibas-as-diferencas-entre-os-certificados-a1-e-a3/)
