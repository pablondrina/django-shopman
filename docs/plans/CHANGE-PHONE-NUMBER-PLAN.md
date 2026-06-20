# WP futuro — "Mudar número de telefone" (mantendo a conta)

> **Origem (Pablo, 2026-06-20):** na conta, o atual "Trocar telefone" é, na verdade, **trocar de
> conta** (login com outro número = outra identidade; telefone é único/identidade). Existem DUAS
> features distintas: **trocar de conta** (temos) e **mudar número mantendo a conta/histórico** (não
> temos). Decisão: documentar como WP; **só fazer se valer a pena**, após avaliação minuciosa do
> quanto o Core precisa ser tocado.

## Avaliação de impacto no Core (preliminar, 2026-06-20)
- **guestman (Core): NÃO precisa mudar.** `customer.update()` já aceita `phone` (`UPDATABLE_FIELDS`);
  `identity.ensure_contact_point()` sincroniza o `ContactPoint` (fonte de verdade do lookup
  `get_by_phone`); o vínculo com o User Django é por **`customer.uuid`** (`CustomerUser`), não por
  telefone — trocar o número **não quebra o login**.
- **doorman (Core): ponto em aberto — talvez precise de 1 adição aditiva.** Hoje o único verify é
  `verify_for_login()`, que **faz `login()` junto**. Para "mudar número" é preciso **provar posse do
  número novo SEM logar nele** (senão vira "trocar de conta"). Opções a avaliar antes de decidir:
  1. **Compor sem tocar Core:** existe algum caminho de validar o código sem o `login()`? (ler
     `verification.py` a fundo — se houver um `_verify`/`check` interno reutilizável, expor via
     storefront sem mudar doorman.)
  2. **Adição cirúrgica no doorman:** um `verify_code(target, code)` "verify-only" (sem login).
     Aditivo, pequeno — mas Core é sagrado, exige aval explícito.
  > **Insight:** o **step-up de reautenticação** (excluir/exportar) NÃO tem esse problema — é o
  > **mesmo número** do usuário logado, então pode reusar `verify_for_login` (re-login da MESMA conta
  > é inócuo). É só "mudar número" que precisa do verify-sem-login.
- **storefront/shop: orquestração + UI novas** — informar número novo → OTP → confirmar; rejeitar se
  o número já pertence a outra conta (ou oferecer merge — futuro); atualizar `Customer.phone` +
  `ContactPoint` atômico.

## Esboço de WP (quando priorizar)
1. Avaliar item (1) acima — se der pra evitar tocar o doorman, fazer assim.
2. Se inevitável: adicionar `verify_code` verify-only ao doorman (com aval do Pablo).
3. Storefront: tela/sheet "Mudar meu número" (informar novo → OTP → confirmar), validação inline,
   rejeição de número já usado, copy omotenashi.
4. Serviço de orquestração: verifica posse → `customer.update(phone)` + `ensure_contact_point` (atômico).
5. Testes: posse verificada, número duplicado rejeitado, histórico/uuid preservados, login intacto.

## Relacionados
- Copy do "trocar de conta" já corrigida no Lote 3 da auditoria (deixar honesto que é entrar com outra conta).
- [[project_storefront_audit_fixes]] · `docs/plans/STOREFRONT-AUDIT-FIXES-PLAN.md`.
