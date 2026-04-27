# Filtro de Design de Superfícies

Este filtro complementa o framework de omotenashi. Omotenashi responde
se a interação cuida bem da pessoa. Este filtro responde se a superfície
foi desenhada com clareza, consistência, foco, acessibilidade e maturidade.

Use em qualquer UI do Shopman: storefront, backstage, KDS, POS, pedidos,
produção, fechamento e admin customizado. A regra é simples: uma tela só
passa quando parece inevitável, isto é, quando cada tamanho, espaçamento,
ícone, cor, palavra, estado e fluxo tem motivo claro.

## 1. Princípios

- **Foco primeiro**: em cada tela deve ser óbvio o que a pessoa pode fazer
  agora. Elementos secundários existem, mas não competem com a ação principal.
- **Um jeito canônico**: não criar variantes visuais para a mesma intenção.
  Um tipo de botão, badge, campo, modal, card e navegação por propósito.
- **Mobile-first real**: a tela deve funcionar apertada antes de funcionar
  larga. Desktop pode redistribuir espaço, nunca inventar outro produto.
- **WhatsApp-first quando cliente final**: telefone, status, recuperação e
  contato devem respeitar o WhatsApp como canal preferencial, sem bloquear SMS
  ou internacional quando o negócio exige.
- **Penguin UI como meio canônico**: tokens, cores, radius, fontes, botões,
  badges e surfaces vêm do design system. Classe avulsa só quando há lacuna
  real e documentada.
- **Acessibilidade antes de decoração**: contraste, alvo de toque, labels,
  foco, leitura por teclado e semântica vencem efeito visual.
- **Sem ornamento sem função**: remover textos, badges, ícones, cards,
  divisórias e microcopy que não orientem, tranquilizem, previnam erro ou
  acelerem uma decisão.

## 2. Tipografia

- Usar o menor conjunto possível de tamanhos e pesos.
- Reservar escala grande para hierarquia real: título de página ou estado
  principal. Painéis, cards, drawers e navs usam texto mais compacto.
- Evitar peso alto repetido. Normalmente:
  - título principal: `font-semibold`;
  - labels e CTAs: `font-medium` ou `font-semibold`;
  - corpo e ajuda: peso normal.
- Não usar fonte monospace em campos de telefone, OTP ou preço salvo quando a
  legibilidade tabular for necessária. Preferir `tabular-nums`.
- Evitar `text-[10px]` e microtipo em navegação, badges e legendas. O menor
  texto de UI deve continuar legível em mobile.
- Não escalar fonte com viewport (`vw`). Responsividade deve vir de layout,
  quebra de linha e densidade, não de tipografia elástica.

Checklist:

- O usuário consegue escanear a tela em 3 segundos?
- Há no máximo 2 ou 3 níveis tipográficos no mesmo painel?
- O menor texto é legível no celular?
- Alguma palavra longa estoura botão, badge, card ou nav?

## 3. Ícones

- Ícones devem ter tamanho padronizado por função, não por gosto local.
- Usar classes canônicas:
  - `icon-sm` para legendas, badges e microações;
  - `icon-md` para botões e ações comuns;
  - `icon-lg` para cards ou títulos compactos;
  - `icon-xl` ou `icon-display` só para estados vazios ou hero states.
- Ícone em botão deve estar visualmente alinhado ao texto e não deformar altura.
- Ícones decorativos devem ser `aria-hidden="true"`.
- Preferir Material Symbols ou biblioteca adotada pela superfície. Não misturar
  famílias de ícones sem motivo.
- Ícone colorido só quando a cor comunica estado. Caso contrário, monocromático.

Checklist:

- Todos os ícones parecem da mesma família?
- O ícone de busca, nav, SMS, WhatsApp, carrinho e voltar têm proporção similar?
- Algum ícone aumenta badge, botão ou linha de forma desigual?

## 4. Espaçamento e Composição

- Espaçamento deve seguir ritmo previsível. Repetir padrões:
  - blocos compactos: `gap-2` / `space-y-2`;
  - grupos de formulário: `gap-2` para label + ajuda + input;
  - seções: `space-y-5` ou `space-y-6`;
  - listas/cards: `gap-3` ou `gap-4`.
- Paddings horizontais mobile devem priorizar leitura: geralmente `px-4` ou
  `px-5`, evitando cartões apertados e evitando margens excessivas.
- Não colocar card dentro de card, salvo modal ou item repetido com motivo.
- Cards não podem deformar por falta de espaço vertical. Se badge, preço e
  CTA competem, a composição deve redistribuir por breakpoint.
- Usar `flex-wrap`, `min-w-0`, `shrink-0`, `w-fit`, `aspect-ratio`, `min-h` e
  breakpoints para impedir sobreposição.
- Elementos fixos, sticky e drawers precisam de z-index documentado e testado.

Checklist:

- A tela respira sem desperdiçar espaço?
- O mesmo tipo de bloco usa o mesmo padding?
- Há sobreposição em desktop, mobile, drawer, sticky bar ou bottom nav?
- Badges, preços e CTAs se acomodam sem abarrotar?

## 5. Cor, Contraste e Estado

- Usar tokens Penguin UI. Evitar paleta paralela por tela.
- Contraste de texto deve ser confortável e acessível antes de bonito.
- Texto secundário não pode ficar claro demais. Ajuda e metadados devem ser
  discretos, mas legíveis.
- Cores semânticas comunicam estado:
  - sucesso: disponível, confirmado, pronto;
  - aviso: atenção, prazo, estoque baixo;
  - perigo: erro, bloqueio, ação destrutiva;
  - neutro: informação sem urgência.
- Não depender só de cor: texto, ícone ou posição devem reforçar o estado.
- Evitar gradientes e dominância de uma cor só quando não agregam clareza.

Checklist:

- A UI continua compreensível em baixa luminosidade?
- O estado é claro para alguém daltônico ou sem perceber cor?
- Há texto cinza demais sobre fundo claro?
- Algum badge parece CTA ou algum CTA parece badge?

## 6. Badges

- Badge é estado ou atributo curto. Não é frase, não é explicação e não é CTA.
- Todos os badges devem usar contrato canônico: radius, altura, fonte, padding
  e cor semântica consistentes.
- Evitar badge redundante quando a informação aparece melhor em seção dedicada.
  Exemplo: alergênicos e restrições pertencem ao conteúdo estruturado da PDP,
  não ao topo do cardápio se não ajudam a decisão imediata.
- Badge com ícone só se o ícone melhorar leitura. Caso contrário, texto curto.
- Badge de promoção deve se acomodar perto do preço sem sobrepor botão.

Checklist:

- O badge cabe em uma linha no menor viewport?
- A altura de badges irmãos é igual?
- O badge adiciona decisão ou só polui?

## 7. Formulários e Entradas

- Campo deve deixar claro o que pedir, por que pedir e como corrigir.
- Labels são obrigatórios. Placeholder não substitui label.
- Ajuda curta fica antes do campo quando reduz ansiedade; erro fica próximo ao
  campo quando corrige ação.
- Evitar zoom automático no iOS: inputs precisam de `font-size >= 16px`.
- Máscara é ajuda, não regra de confiança. Backend normaliza e valida.
- Prefixos não editáveis podem ficar dentro do campo como adornment quando
  reduzem ruído visual, desde que não pareçam selecionáveis.
- Se existir exceção real, o caminho deve ser explícito. Exemplo: Brasil por
  padrão com `+55`; número internacional via "Usar número de outro país".
- Não criar controle falso. Se parece seletor, precisa funcionar como seletor.

Checklist:

- Dá para preencher sem ler instrução longa?
- O erro diz como resolver?
- O campo transmite o dado certo para o backend canônico?
- O controle visual promete algo que não existe?

## 8. Fluxos e Foco

- Cada tela deve ter uma intenção dominante.
- Fluxos longos devem revelar um passo por vez quando isso reduz carga mental.
- A ação principal deve ser maior, mais clara e mais próxima do contexto.
- Ações secundárias devem existir sem competir: ghost, link ou disclosure.
- Recuperação de erro deve ter próximo passo. Nunca dead-end.
- Estados vazios devem orientar a próxima ação, não apenas declarar ausência.
- Estado de loading deve proteger contra duplo clique e explicar espera quando
  a espera é perceptível.

Checklist:

- Se eu remover tudo que não ajuda a próxima ação, o que sobra?
- A tela tem mais de uma ação competindo visualmente?
- Toda falha tem saída?
- O fluxo volta para onde o usuário esperava?

## 9. Conteúdo Visual e Produto

- Imagem deve ajudar a decidir ou reconhecer, não apenas decorar.
- PDP precisa mostrar foto do produto cedo, mas sem sequestrar a tela inteira
  no mobile. Preferir aspect ratio mais horizontal quando melhora decisão.
- Fotos quebradas são falha de produto, não detalhe técnico.
- Hero e imagens de fundo precisam preservar legibilidade do conteúdo.
- No backstage, conteúdo visual deve ser funcional: estação, pedido, status,
  risco, prioridade, operador.

Checklist:

- A imagem mostra o produto/estado real?
- O usuário consegue decidir melhor por causa dela?
- Há fallback elegante para imagem ausente?

## 10. Responsividade e Densidade

- Mobile-first: uma coluna, foco, CTA claro, alvo de toque mínimo.
- Desktop: usar espaço para reduzir scroll e melhorar comparação, sem apertar
  componentes na mesma linha.
- Backstage pode ser mais denso que storefront, mas não pode ser confuso.
- Cozinha e balcão pedem leitura à distância, contraste forte e ações grandes.
- Listas operacionais devem priorizar ordenação, filtros e status, não ornamento.

Checklist:

- Mobile tem a mesma capacidade essencial do desktop?
- Desktop usa largura extra para clareza, não para encher a tela?
- Operador consegue agir rápido sob pressão?

## 11. Backstage: Aplicação Específica

O backstage deve herdar o mesmo rigor visual do storefront, mas com outra
densidade. O cliente precisa desejar e confiar. O operador precisa perceber,
decidir e agir sem hesitar.

Regras para backstage:

- Dark-first quando a tela fica aberta por longos períodos.
- Um shell comum para pedidos, KDS, POS, produção e fechamento.
- Navegação persistente e previsível; nenhuma área deve parecer ilha.
- Status e prioridade sempre visíveis antes de detalhes.
- Ação destrutiva ou irreversível sempre separada, confirmada e com motivo.
- Pedidos atrasados, alergênicos, ruptura e pagamento pendente devem aparecer
  antes de informação administrativa.
- Componentes de operação devem ter alvos maiores que componentes editoriais.
- Tabelas precisam de densidade controlada: cabeçalho fixo, estados visíveis,
  vazios úteis e filtros óbvios.
- O sistema deve proteger o operador de erro: defaults seguros, confirmação
  contextual, bloqueio de ações inválidas e feedback imediato.

## 12. Filtro de Aceite

Antes de concluir qualquer UI, responder:

1. **Foco**: qual é a ação principal desta tela?
2. **Hierarquia**: o olhar chega primeiro no que importa?
3. **Consistência**: tipografia, ícones, badges, botões e campos seguem o mesmo
   contrato das outras superfícies?
4. **Espaço**: há respiro suficiente sem desperdiçar área útil?
5. **Contraste**: tudo que precisa ser lido passa confortavelmente?
6. **Acessibilidade**: funciona com teclado, leitor, toque e baixa visão?
7. **Responsividade**: mobile e desktop não quebram nem sobrepõem?
8. **Estado**: loading, vazio, erro, sucesso e bloqueio têm tratamento claro?
9. **Conteúdo**: toda palavra, imagem, ícone e badge ajuda uma decisão?
10. **Canônico**: existe outro jeito concorrente de resolver a mesma coisa?

Se qualquer resposta for fraca, a UI ainda não está pronta.

## 13. Anti-Padrões

- Criar novo tamanho de fonte para resolver um caso local.
- Usar ícone menor ou maior porque "coube melhor" sem atualizar o contrato.
- Badge como decoração.
- Texto explicativo dizendo como usar a UI quando a própria UI deveria guiar.
- Placeholder como label.
- Card dentro de card.
- Botão primário para ação secundária.
- CTA competindo com outro CTA na mesma hierarquia.
- `text-[10px]` para fazer caber.
- Elemento sticky sem z-index testado contra drawer, nav e modal.
- Formulário que pede dado sem explicar propósito.
- Controle que parece editável/selecionável mas não é.
- Estado vazio que não oferece próximo passo.
- Erro que descreve o problema sem caminho de recuperação.
- Repetir informação em dois lugares próximos sem ganho claro.

## 14. Aprendizados Recentes do Storefront

- Prefixo de telefone brasileiro fica melhor como adornment interno não
  editável, com internacional explícito como caminho separado.
- Input de telefone deve ter `font-size` suficiente para evitar zoom automático
  no iOS.
- Bottom nav e legendas não devem usar microtipo inferior ao menor texto padrão.
- Ícones precisam ser proporcionais cross-site; o ícone de busca não pode virar
  exceção visual.
- Badges de tempo e desconto precisam de altura/padding padronizados; ícones em
  badges só quando não deformam o conjunto.
- PDP deve mostrar imagem cedo, mas com proporção que preserve compra rápida no
  mobile.
- Informações de decisão remota devem ser estruturadas: ingredientes,
  alergênicos, restrições, nutrição, conservação, peso e medidas.
- Dados úteis para busca e SEO devem nascer no seed/modelo, não só no template.
- Copy repetida na mesma tela reduz confiança.
- Travessão usado por hábito deve ser removido; preferir frase fluida ou bullet
  fino quando separar itens for realmente útil.
- Foto quebrada, overflow horizontal, z-index incorreto e sobreposição são
  regressões de design, não detalhes cosméticos.
