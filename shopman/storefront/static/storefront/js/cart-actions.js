/*
 * Storefront cart actions.
 *
 * Small canonical bridge for Alpine-driven cart controls. Templates still own
 * their local UI state, but network transport, CSRF, stock-error modal mounting,
 * haptics, and failure notifications live here so cart cards do not drift.
 */
(function () {
  "use strict";

  var ns = window.ShopmanCart || {};

  function csrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.content : "";
  }

  function notify(variant, message) {
    window.dispatchEvent(
      new CustomEvent("notify", {
        detail: { variant: variant || "info", message: message || "" },
      })
    );
  }

  function triggerCartUpdated() {
    if (window.htmx) window.htmx.trigger(document.body, "cartUpdated");
  }

  var projectionRefreshTimer = null;

  function scheduleProjectionRefresh(delayMs) {
    if (!window.htmx) return;
    window.clearTimeout(projectionRefreshTimer);
    projectionRefreshTimer = window.setTimeout(function () {
      triggerCartUpdated();
    }, delayMs == null ? 800 : delayMs);
  }

  function setBadgeCount(count) {
    var badge = document.getElementById("cart-badge-header");
    if (!badge || count == null || Number.isNaN(count)) return;

    if (count > 0) {
      badge.textContent = String(count);
      badge.classList.remove("hidden");
      badge.classList.add("inline-flex");
    } else {
      badge.textContent = "";
      badge.classList.remove("inline-flex");
      badge.classList.add("hidden");
    }
  }

  async function cartPayloadFromResponse(resp) {
    var contentType = resp.headers.get("Content-Type") || "";
    if (contentType.indexOf("application/json") === -1) return null;
    try {
      return await resp.json();
    } catch (_err) {
      return null;
    }
  }

  function setText(selector, text) {
    document.querySelectorAll(selector).forEach(function (el) {
      el.textContent = text;
    });
  }

  function applyMinimumOrder(progress) {
    var hasMinimumDom = document.querySelector("[data-cart-minimum]") != null;
    var hasMinimumPayload = !!progress;

    if (hasMinimumDom !== hasMinimumPayload) {
      scheduleProjectionRefresh();
      return;
    }

    if (!progress) return;
    setText("[data-cart-minimum-remaining]", progress.remaining_display || "");
    setText("[data-cart-minimum-total]", progress.minimum_display || "");
    document.querySelectorAll("[data-cart-minimum-progress]").forEach(function (el) {
      el.style.width = String(progress.percent || 0) + "%";
    });
  }

  function applyCartPayload(payload) {
    if (!payload || !payload.cart) return;

    var cart = payload.cart;
    var count = Number(cart.count || 0);
    var subtotalDisplay = cart.subtotal_display || "R$ 0,00";
    var grandTotalDisplay = cart.grand_total_display || subtotalDisplay;

    setBadgeCount(count);
    setText("[data-cart-items-count]", String(count));
    setText("[data-cart-items-label]", count === 1 ? "item" : "itens");
    setText("[data-cart-subtotal-display]", subtotalDisplay);
    setText("[data-cart-grand-total-display]", grandTotalDisplay);
    applyMinimumOrder(cart.minimum_order_progress);

    window.dispatchEvent(
      new CustomEvent("shopman-cart-summary", { detail: cart })
    );
  }

  function mountStockErrorModal(html) {
    var sink = document.getElementById("stock-error-modal");
    if (!sink) {
      notify("danger", "Não foi possível mostrar o aviso de estoque.");
      return false;
    }
    sink.innerHTML = html;
    if (window.htmx) window.htmx.process(sink);
    if (window.Alpine) window.Alpine.initTree(sink);
    return true;
  }

  function stockWord(qty) {
    return qty === 1 ? "unidade disponível" : "unidades disponíveis";
  }

  ns.setQty = async function setQty(options) {
    var opts = options || {};
    var body = new FormData();
    body.append("sku", opts.sku || "");
    body.append("qty", String(opts.qty == null ? 0 : opts.qty));

    try {
      var resp = await fetch(opts.url, {
        method: "POST",
        headers: {
          "X-CSRFToken": csrfToken(),
          "Accept": "application/json, text/html;q=0.8",
        },
        body: body,
      });

      if (resp.ok) {
        var payload = await cartPayloadFromResponse(resp);
        if (!payload || payload.ok !== true) {
          notify("warning", "Resposta inesperada ao atualizar o carrinho.");
          return { ok: false, contractError: true, response: resp };
        }
        applyCartPayload(payload);
        if (opts.refreshProjection) triggerCartUpdated();
        if (window.triggerHaptic) window.triggerHaptic.light();
        return { ok: true, payload: payload, response: resp };
      }

      if (resp.status === 422 && resp.headers.get("X-Shopman-Error-UI") === "1") {
        mountStockErrorModal(await resp.text());
        if (window.triggerHaptic) window.triggerHaptic.error();
        return { ok: false, richError: true, response: resp };
      }

      notify("warning", opts.warningMessage || "Não foi possível atualizar o carrinho. Tente novamente.");
      return { ok: false, response: resp };
    } catch (_err) {
      notify("danger", "Sem conexão. Verifique sua internet.");
      if (window.triggerHaptic) window.triggerHaptic.error();
      return { ok: false, networkError: true };
    }
  };

  ns.line = function line(options) {
    var opts = options || {};
    return {
      qty: Number(opts.qty || 0),
      max: opts.max == null ? 99 : Number(opts.max),
      canAdd: opts.canAdd !== false,
      lineTotalDisplay: opts.lineTotalDisplay || "",
      visible: true,
      busy: false,
      get effectiveMax() {
        return Math.min(99, Number(this.max || 0));
      },
      get showMaxHint() {
        return this.qty > 0 && this.qty >= this.effectiveMax - 2 && this.effectiveMax > 0;
      },
      async set(next) {
        if (this.busy) return;
        var ceiling = this.effectiveMax;
        var target = Number(next || 0);
        if (target > ceiling) {
          notify("warning", "Apenas " + ceiling + " " + stockWord(ceiling) + ".");
          target = ceiling;
        }
        target = Math.max(0, target);

        var prev = this.qty;
        this.busy = true;
        this.qty = target;
        var result = await ns.setQty({
          url: opts.url,
          sku: opts.sku,
          qty: target,
          warningMessage: opts.warningMessage,
          refreshProjection: opts.refreshProjection || (
            target === 0 && opts.refreshProjectionOnZero
          ),
        });
        if (result.ok && result.payload && result.payload.line) {
          this.qty = Number(result.payload.line.qty || target);
          this.lineTotalDisplay = result.payload.line.line_total_display || this.lineTotalDisplay;
          if (this.qty === 0) {
            this.visible = false;
            if (opts.undoEvent) {
              window.dispatchEvent(new CustomEvent("notify", {
                detail: {
                  variant: "info",
                  message: (opts.name || opts.sku || "Item") + " removido.",
                  actionLabel: "Desfazer",
                  actionEvent: opts.undoEvent,
                  actionDetail: { sku: opts.sku, qty: prev },
                },
              }));
            }
          }
        } else if (!result.ok) {
          this.qty = prev;
        }
        this.busy = false;
        return result;
      },
    };
  };

  ns.refresh = triggerCartUpdated;
  ns.refreshSoon = scheduleProjectionRefresh;
  ns.notify = notify;
  ns.mountStockErrorModal = mountStockErrorModal;
  ns.applyCartPayload = applyCartPayload;

  window.ShopmanCart = ns;
})();
