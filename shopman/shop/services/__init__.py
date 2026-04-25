"""
Shopman services — business logic using Core services + adapters.

Services are the heart of the architecture. Each service:
- Encapsulates business logic as plain functions (not classes)
- Documents which Core services and adapters it uses
- Is testable in isolation (adapter mockable)
- Is either SYNC (returns result) or ASYNC (creates Directive)

SYNC services:
    production.reserve_materials(wo) — WP-S5 hook (planejamento)
    production.emit_goods(wo)        — WP-S5 hook (encerramento)
    production.notify(wo, event)     — WP-S5 lifecycle log
    stock.hold(order)            — Reserve stock (expands bundles)
    stock.fulfill(order)         — Fulfill holds
    stock.release(order)         — Release holds (cancellation)
    stock.revert(order)          — Return stock (returns)
    payment.initiate(order)      — Create payment intent
    payment.capture(order)       — Capture payment
    payment.refund(order)        — Refund (smart no-op)
    customer.ensure(order)       — Resolve/create customer
    sessions.create/modify/commit — Canonical surface-to-Orderman session writes
    fulfillment.create(order)    — Create fulfillment record
    fulfillment.update(f, s)     — Update fulfillment status
    pricing.resolve(sku, qty)    — Resolve price
    cancellation.cancel(order)   — Cancel order (WP-S6: único caminho; Flow libera stock)
    kds.dispatch(order)          — Route items to KDS instances
    kds.on_all_tickets_done(order) — Transition to READY
    checkout.process(...)        — Validate + modify session + commit

ASYNC services (create Directives):
    notification.send(order, t)  — Queue notification
    loyalty.earn(order)          — Queue loyalty points
    fiscal.emit(order)           — Queue NFC-e emission
    fiscal.cancel(order)         — Queue NFC-e cancellation
"""
