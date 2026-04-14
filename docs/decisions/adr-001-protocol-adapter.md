# ADR-001: Protocol/Adapter em vez de imports diretos

**Status:** Aceito
**Data:** 2025-01-20
**Contexto:** Comunicacao entre apps da suite

---

## Contexto

A suite é composta por apps Django independentes com “personas” canônicas (orderman, stockman, craftsman, offerman, guestman, doorman, utils). Cada app é um pacote pip instalável separadamente. Precisamos que os apps colaborem — orderman precisa verificar disponibilidade (stockman), buscar preços (offerman), resolver clientes (guestman) — sem criar acoplamento direto.

A alternativa mais simples seria `from shopman.stockman.service import StockService` dentro do orderman. Isso criaria uma dependência hard entre pacotes.

## Decisao

Toda comunicacao entre apps usa `typing.Protocol` (PEP 544) com `@runtime_checkable`:

1. O app **consumidor** define o Protocol (contrato) no seu proprio codigo
2. O app **provedor** implementa um Adapter no seu proprio codigo
3. A ligacao e feita via settings (dotted path) ou registry (`AppConfig.ready()`)

```python
# framework/shopman/protocols.py — consumidor define o contrato
@runtime_checkable
class StockBackend(Protocol):
    def check_availability(self, sku: str, quantity: Decimal, ...) -> AvailabilityResult: ...

# framework/shopman/backends/stock.py — adapter que conecta ao stockman
class StockmanAdapter:
    def check_availability(self, sku: str, quantity: Decimal, ...) -> AvailabilityResult:
        return StockService.check(sku, quantity)

# settings.py — ligacao via config
SHOPMAN_STOCK_BACKEND = "shopman.inventory.adapters.stockman.StockmanAdapter"
```

## Consequencias

### Positivas

- **Deploy independente:** Cada app pode ser instalado sem os demais. Testes rodam com MockBackends
- **Substituibilidade:** Trocar stockman por outro sistema de estoque requer apenas um novo adapter, sem tocar no orderman
- **Testabilidade:** `MockStockBackend`, `MockPaymentBackend` etc. permitem testes unitarios isolados sem dependencias externas
- **Sem dependencias circulares:** Cada app depende apenas de `utils` e do proprio codigo
- **Type checking:** `@runtime_checkable` + type hints completos permitem validacao em runtime e IDE support

### Negativas

- **Indireccao:** Mais arquivos (protocols.py, adapters/, conf.py). Requer navegar mais para entender o fluxo completo
- **Duplicação de dataclasses:** `CustomerInfo` pode existir em mais de um pacote/protocolo por desenho (contratos locais), mas as fronteiras devem permanecer explícitas (Protocol/Adapter).
- **Config manual:** O settings.py do projeto precisa ligar todos os backends. Erro de configuracao so aparece em runtime

### Mitigacoes

- `seed_nelson` demonstra configuracao completa
- Testes de integracao validam que adapters satisfazem os protocols
- Defaults sensiveis em `conf.py` (ex: `ConsoleSender` para gating em dev)
