# Odoo POS — Dossiê (deep-dive ao vivo)

> Benchmark #4. Estudado **ao vivo** em `demo.odoo.com` (Bakery Shop, base de demonstração
> Odoo 18) em 2026-06-08, tela a tela, foco na **tela de pagamento** — o gap que a
> [synthesis.md](synthesis.md) §5 marcava como "maior prioridade do que falta". Odoo é o único
> PDV web 100% open source e o único explorável ao vivo sem trial gated.
>
> Motivação imediata: validar/refutar a direção **"Conta + Instrumento"** do nosso redesign de
> pagamento (commit `90cb8dc7`). Resultado: **Odoo confirma a direção** e sugere refinamentos de
> densidade. Detalhe abaixo.

---

## 1. Layout do register (tela de venda)

Duas colunas, **ticket à esquerda** (é o nosso layout atual herdado, e o oposto do Shopify
cart-à-direita):

- **ESQUERDA = o pedido.** Linhas do pedido (produto · qty · preço) no topo; `Taxes` + **`Total`**
  em destaque; abaixo **Customer** / **Note**; e — o ponto-chave — o **numpad SEMPRE presente**,
  embutido no painel do pedido, com **modos `Qty` / `% ` / `Price`** (a 4ª coluna alterna o que o
  numpad edita na linha selecionada: quantidade, desconto, ou preço unitário). CTA **`Payment`**
  roxo, largura cheia, no rodapé da coluna.
- **DIREITA = a grade de produtos**, com abas de categoria no topo (`Breads` / `Pastries`), busca +
  leitor de código de barras na barra superior.

> **Insight transversal:** o numpad do Odoo é **um instrumento único e persistente** que muda de
> *modo* conforme o contexto — Qty/%/Price no register, valor-do-tender no pagamento. Mesma posição,
> mesma memória muscular. Não há "numpad que aparece e some".

---

## 2. Tela de pagamento — anatomia (o alvo)

Acessada pelo CTA `Payment`. **Duas colunas**, e a divisão é o oposto da intuição "formulário":

### ESQUERDA — o instrumento (compacto, ~⅓ da largura)
1. **Lista vertical de métodos** no topo: `Cash` / `Card` / `Customer Account`, cada um com ícone.
   **Tocar um método = adiciona uma _linha de pagamento_** com o valor que falta. Não são tiles
   grandes — é uma **lista slim** que escala pra muitos métodos.
2. Linha **`Customer`** + **`Invoice`** (toggle de nota fiscal).
3. **Numpad** com **`+10` / `+20` / `+50` como 4ª coluna verde** — as "cédulas"/quick-adds
   **fundidas no próprio numpad**, não num bloco separado. Mais `+/-`, `0`, `.`, backspace.
4. Rodapé: **`Back`** + um CTA grande que é **contextual**:
   - **sem linha de pagamento** → mostra o método padrão (`Cash`) = atalho "pagar tudo nessa forma
     em 1 toque";
   - **com linha cobrindo o total** → vira **`Validate`**.

### DIREITA — o valor (dominante, ~⅔ da largura)
- O **valor da venda GIGANTE e centralizado** (`$45.60` ocupando metade da tela). É a âncora.
  **Estável**: permanece o total mesmo quando há troco — NÃO colapsa pra zero. Fica **cinza-claro**
  quando a linha selecionada está em estado "auto" (intocada) e **preto/bold** quando editada.
- Abaixo do valor, as **linhas de pagamento** acumulam (`Cash ···· $95.60` com `✕` pra remover; a
  selecionada tem borda azul).
- Mais abaixo, **`Change`** (ou `Remaining`) em **verde** — o troco/restante derivado.

### Mecânica observada ao vivo
- Tocar `Cash` → linha `Cash $45.60` (= o que falta) + CTA vira `Validate`.
- `+50` no numpad → linha vira `$95.60`, e **`Change $50.00`** aparece em verde. Os `+N`
  **acumulam** o recebido (cliente entregou notas).
- Split: remover a linha (`✕`), tocar `Card`, ajustar valor no numpad → some o restante numa
  segunda forma. **O valor gigante permanece $45.60 o tempo todo** (a âncora não se mexe).

---

## 3. Confronto direto com nosso "Conta + Instrumento" (`90cb8dc7`)

| Decisão nossa | Odoo faz igual? | Nota |
|---|---|---|
| Herói = **total estável**, nunca vira 0,00 | ✅ **Idêntico** | Odoo é até mais radical: o valor ocupa ~½ tela. **Valida o fix do "0,00 em destaque".** |
| **Numpad universal** edita o tender selecionado | ✅ **Idêntico** | Era exatamente o ponto do Pablo ("no split, precisa do numpad de qualquer forma"). |
| **Linhas de tender** acumulam, editáveis, removíveis | ✅ Idêntico | Selecionada destacada; `✕` remove. |
| **Cédulas/quick-add acumulam** o recebido | ✅ Idêntico (`+10/+20/+50`) | Mas Odoo **funde no numpad** (4ª coluna), não um bloco separado. |
| Leitura adaptativa **Faltam → Troco → Pronto** | ✅ Equivalente | Odoo: `Change`/`Remaining` em verde sob as linhas. |
| Split é nativo (não um modo) | ✅ Idêntico | Tocar forma pega o restante; ajusta no numpad. |

**Veredito: a direção "Conta + Instrumento" É o modelo do Odoo.** O deep-dive **valida** a
reconstrução `90cb8dc7` por evidência (não só por dedução).

### Refinamentos que o Odoo sugere (candidatos, decisão do Pablo)
1. **Valor ainda mais dominante.** Odoo dedica ~½ da tela ao número. Nosso herói é grande mas
   divide a coluna esquerda com as linhas. Dá pra empurrar o valor pra um peso maior.
2. **Fundir as cédulas no numpad** (coluna lateral de `+R$`), em vez de uma grade de cédulas
   separada acima do numpad — um único instrumento, mais denso, menos seções.
3. **Métodos como lista slim** (não tiles grandes) — escala melhor se um dia houver muitos métodos;
   hoje (Dinheiro/PIX/Cartão) tiles ainda cabem, é questão de gosto/densidade.
4. **CTA contextual** "pagar-tudo-na-forma-padrão" quando não há tender (atalho de 1 toque pro caso
   comum), virando "Finalizar" quando coberto.
5. **Numpad com modos no register** (`Qty`/`%`/`Price`) — fora do escopo da tela de pagamento, mas
   é um padrão forte pro nosso painel de comanda (hoje temos Qty/Desc% separados).

### Onde podemos ser MELHORES que o Odoo
- **Omotenashi/acessibilidade:** Odoo é denso e funcional, mas frio (tipografia ERP, zero acolhimento).
  Nosso herói + leitura adaptativa com cor/linguagem acolhedora ("Pronto para finalizar") é mais quente.
- **PIX-first BR:** Odoo não tem nuance de PIX (QR/copia-e-cola) — nós já temos (PCI SAQ A).
- **Mobile/tablet:** Odoo é desktop-puro; nosso layout empilha com `lg:flex-row` (desktop-first mas
  não desktop-only).

---

## 4. O que NÃO portar
- **Ticket-à-esquerda como dogma:** Odoo usa, mas o Pablo já escolheu **cart-à-direita (Shopify D2)**
  pro register. A tela de pagamento do Odoo é coluna-instrumento-esquerda / valor-direita — isso é
  ortogonal à escolha do register e pode conviver.
- **Densidade fria de ERP:** referência de *mecânica*, não de *tom*. Manter nosso tom omotenashi.

---

## 5. Pendências / não explorado nesta passada
- Mecânica fina de replace-vs-append do numpad (1º dígito substitui, demais acumulam) — observada com
  ruído de timing no live; o comportamento-alvo é claro e já é o nosso (`tenderFresh`).
- Tela de **fechamento de caixa / sessão** (densidade de gestão de turno) — Odoo é referência aqui,
  fica pra um deep-dive de Caixa quando tocarmos nessa tela.
- **Customer selection** — agora **aprofundado em [odoo-customer.md](odoo-customer.md)**
  (deep-dive do "Choose Customer" + Edit Partner + UNSELECT, 2026-06-10).

Ver também [[synthesis.md]] (decisões cruzadas) e a memória `project_wp7_pos_status.md` (entrada do
commit `90cb8dc7` "Conta + Instrumento").
