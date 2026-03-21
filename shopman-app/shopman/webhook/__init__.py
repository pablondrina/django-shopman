"""
Shopman Webhook contrib — Recebe webhooks do Manychat (inbound).

Processa ações do agente Nice (via Manychat custom actions / external requests)
e delega para os services do Shopman (Session, Commit, Order).

Ações suportadas:
- new_order: Abre Session + adiciona items
- add_item: Adiciona item a Session existente
- commit_order: Fecha Session → Order
- check_status: Consulta status de Order
- list_menu: Lista produtos publicados
"""
