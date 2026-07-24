# drawer-test — teste físico de gaveta + térmica (staging)

Ferramenta standalone (Python 3, só stdlib) para validar o hardware da loja
**antes** da Fase C (impressão integrada ao PDV). Não depende do Django nem do
staging: roda no computador da loja, falando direto com a impressora.

## O que ela prova

1. A impressora térmica responde (rede, CUPS ou USB).
2. O pulso ESC/POS abre a gaveta (cabo RJ11 na porta **DK** da impressora).
3. Corte de papel e um cupom de teste com acentuação.

Se os três funcionam, o hardware está pronto — a Fase C só acrescenta o
software (agente local de impressão consumindo os jobs do backstage).

## Uso rápido

```bash
# Impressora de rede (Epson/Elgin/Bematech, porta RAW 9100):
python3 drawer_test.py --network 192.168.0.50 --receipt

# Só abrir a gaveta, sem imprimir:
python3 drawer_test.py --network 192.168.0.50 --kick-only

# Impressora instalada no macOS (CUPS): descubra a fila com `lpstat -p`
python3 drawer_test.py --cups EPSON_TM_T20 --receipt

# Gaveta não abre? Teste o outro pino:
python3 drawer_test.py --network 192.168.0.50 --kick-only --pin 5
```

## Descobrir o IP da impressora

Segure o botão FEED ao ligar a impressora → ela imprime a página de
auto-teste com IP/porta. A porta RAW padrão é 9100.

## Checklist do QA físico (para o gate `omotenashi.manual`)

- [ ] Cupom de teste imprimiu legível (acentos ok)
- [ ] Gaveta abriu no pulso (anotar pino: 2 ou 5)
- [ ] Corte de papel funcionou
- [ ] Anotar modelo da impressora + IP/fila para a config do terminal
      (`PosTerminal.metadata.hardware.printer` / `.cash_drawer`)
