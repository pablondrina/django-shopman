# Odoo POS — Modal de Cliente (deep-dive ao vivo)

> Companheiro do [odoo.md](odoo.md) (que cobre o pagamento). Estudado **ao vivo** em
> `demo6.odoo.com` (Bakery Shop, Odoo 18) em 2026-06-10, a pedido do Pablo: o modal de
> cliente da Venda do nosso POS está aquém e ele quer um redesenho "mais igual ao do
> Odoo". A `odoo.md` §5 marcava a seleção de cliente como **não aprofundada** — este
> dossiê fecha essa lacuna.
>
> Motivação imediata (Pablo): (a) **não existe desassociar cliente** no nosso fluxo;
> (b) há **dois modais de cliente** (header da Venda + Pagamento) duplicados; (c) o
> nosso é um *form leve*, o do Odoo é um *picker de parceiro*.

---

## 1. Anatomia do "Choose Customer" (picker de tela cheia)

Acionado pelo botão **Customer** (canto inferior-esquerdo do register). Abre um overlay
quase full-screen — **não é um diálogo pequeno**, é um gerenciador de parceiros:

- **Barra de topo:** botão **`Create`** (esquerda, destaque) · título **`Choose Customer`**
  · campo de **busca proeminente** `Search Customers...` (direita, com ✕ pra limpar).
- **Lista de parceiros** (rolável), cada linha é rica e multi-coluna:
  - **Nome** (negrito) — e, abaixo, a **empresa** quando houver (ex. "Addison Olson /
    Acme Corporation").
  - **Endereço** completo (coluna própria, quando cadastrado).
  - **Telefone** (ícone 📞) + **e-mail** (ícone ✈/avião de papel).
  - **`Total due: $X`** — saldo do cliente (integração contábil), quando relevante.
  - botão **`☰`** (detalhes) à direita de cada linha.
- **Rodapé:** **`Discard`** full-width.

**Selecionar:** clicar na **linha** (não no ☰) seleciona o cliente e fecha o modal,
voltando ao register.

## 2. O menu por-linha (`☰`)

Abre um pop com três ações **por cliente**:
- **`Edit Details`** → abre o form **Edit Partner** (§4).
- **`All Orders`** → histórico de pedidos daquele cliente.
- **`Deposit money`** → adiantamento/crédito do cliente (contábil).

> Ou seja, o picker do Odoo é também um **mini-CRM operacional**: do balcão dá pra ver
> saldo, histórico e lançar depósito — sem sair pro backend.

## 3. Cliente selecionado + **DESASSOCIAR** (o achado-chave)

- Selecionado, o cliente aparece **no próprio botão `Customer`** do register, agora
  exibindo o **nome em teal** (ex. "Acme Corporation"). Mesmo botão, vira o nome.
- **Reabrindo** o "Choose Customer" com um cliente já associado: ele fica **fixado no
  TOPO da lista, destacado (fundo/texto teal)**, e ganha um botão explícito
  **`✕ UNSELECT`** (ao lado do `☰`). **Esse é o padrão de desassociação** — exatamente o
  que falta no nosso fluxo.

## 4. O form "Edit Partner" (criar/editar)

`Create` (topo) e `Edit Details` (☰) abrem o **mesmo** form, POS-otimizado (um subconjunto
do form de parceiro do backend):
- **Avatar** (placeholder à esquerda) + **Nome** grande, editável.
- Inline sob o nome: **Company/Employer** (🏢) · **E-mail** (✉) · **Telefone** (📞).
- **Address:** Street, Street 2, City / State / ZIP, Country.
- **Barcode** (com `?`) — código de barras do cliente (cartão/fidelidade).
- **Tags** (ex. "B2B", "VIP", "Consulting") — segmentação.
- **TIN** (Tax ID, com `?`) — equivalente ao nosso CPF/CNPJ.
- Rodapé: **`Save`** / **`Discard`**.

## 5. Busca

Filtra a lista enquanto digita (server-side), casando **nome / empresa / telefone /
e-mail** — `"Addison"` → "Addison Olson · Acme Corporation". Botão ✕ limpa.

---

## 6. Confronto com o NOSSO modal de cliente

| Aspecto | Odoo | Nós (hoje) |
|---|---|---|
| Forma | **Picker** full-screen, busca-first | Diálogo pequeno, **form-first** |
| Lista de resultados | rica (nome, empresa, endereço, tel, e-mail, **saldo**) | nome + tel · CPF · e-mail (via `PosCustomerSearch`) |
| Desassociar | **`UNSELECT`** explícito (selecionado fixo no topo) | **não existe** (limpar nome deixa `customerRef` pendurado) |
| Editar/criar | form **Edit Partner** (avatar, endereço, barcode, tags, TIN) | só Nome + WhatsApp inline |
| Por-cliente | **All Orders**, **Deposit money** | — |
| Duplicação | 1 lugar | **2 modais** (header + Pagamento) |
| Selecionado, onde aparece | no próprio botão Customer (nome em teal) | chip no header |

## 7. Direção proposta (pra DISCUTIR — nada implementado)

1. **Um componente compartilhado** de cliente (mata a duplicação header×Pagamento).
2. **Picker-first** (não form-first): busca em evidência → **lista de resultados** mais
   rica (nome, empresa, telefone, CPF, e-mail; e — futuro — saldo/loyalty do Guestman) →
   seleciona; `Create` quando não acha.
3. **Desassociar** = `clearCustomer()` no write-side (dropa `customerRef`/nome/tel/etc.;
   o autosave persiste a remoção) + botão **"Remover cliente"** no cliente associado
   (espelhando o `UNSELECT`, com o selecionado em destaque).
4. **Form de edição** POS-otimizado: nome, WhatsApp, CPF/CNPJ, e-mail, endereço; e,
   alinhado à seção C do redesign, um campo de **crachá/barcode** do cliente (Odoo tem).
5. **Onde podemos ser melhores:** omotenashi/acolhimento (Odoo é frio); CPF/PIX-BR;
   o **histórico/favorito/último pedido** que já temos (memory do Guestman) é mais quente
   que o "All Orders" cru do Odoo — manter e destacar.
6. **Split:** NÃO no modal de cliente — é operação de comanda/pagamento. Parquear como
   feature à parte (liga com `project_pos_split_by_items`).

## 8. Não portar
- O **mini-CRM contábil** completo (Total due / Deposit money / All Orders) — é peso de
  ERP; o nosso Guestman dá o que precisamos (histórico/favorito) de forma mais leve.
- A densidade fria de ERP — referência de **mecânica** (picker, unselect, edit), não de tom.

Ver também [odoo.md](odoo.md) (pagamento) e a memória `project_wp7_pos_status.md`.
