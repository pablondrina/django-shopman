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

  function cartSummaryFromResponse(resp) {
    var rawCount = resp.headers.get("X-Cart-Count");
    if (rawCount == null) return null;

    var subtotalDisplay = resp.headers.get("X-Cart-Subtotal-Display") || "";
    try {
      subtotalDisplay = decodeURIComponent(subtotalDisplay);
    } catch (_err) {
      subtotalDisplay = "";
    }

    return {
      count: Number(rawCount),
      subtotalQ: Number(resp.headers.get("X-Cart-Subtotal-Q") || 0),
      subtotalDisplay: subtotalDisplay,
    };
  }

  function applyCartSummary(resp) {
    var summary = cartSummaryFromResponse(resp);
    if (!summary) return;

    setBadgeCount(summary.count);
    window.dispatchEvent(
      new CustomEvent("shopman-cart-summary", { detail: summary })
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
          "HX-Request": "true",
        },
        body: body,
      });

      if (resp.ok) {
        applyCartSummary(resp);
        if (opts.refreshProjection) triggerCartUpdated();
        if (window.triggerHaptic) window.triggerHaptic.light();
        return { ok: true, response: resp };
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
        });
        if (!result.ok) this.qty = prev;
        this.busy = false;
        return result;
      },
    };
  };

  ns.refresh = triggerCartUpdated;
  ns.notify = notify;
  ns.mountStockErrorModal = mountStockErrorModal;

  window.ShopmanCart = ns;
})();
