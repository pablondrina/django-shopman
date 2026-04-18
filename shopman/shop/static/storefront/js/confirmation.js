/**
 * Planned-hold confirmation UI helpers.
 *
 * Exposed as ``window.*`` factories. Templates reference them as
 * ``x-data="window.confirmationCountdown(iso, display)"`` — Alpine 3's
 * expression scope does not expose bare globals, so the ``window.``
 * prefix is required.
 *
 * Components:
 * - ``window.confirmationCountdown(deadlineIso, deadlineDisplay)``:
 *   ticking "X m YY s" countdown for a ready cart line. When the
 *   deadline lapses, it triggers ``cartUpdated`` so the cart refetches
 *   and the line falls back to "Indisponível".
 * - ``window.confirmationReadyAnnounce(lineId, itemName, deadlineDisplay)``:
 *   per-line one-shot toast on the awaiting → ready transition.
 *   Bookkeeping lives in ``sessionStorage`` so a navigation inside the
 *   storefront does not re-announce the same arrival, but a fresh tab
 *   does. Fires a sticky notify event (requires explicit dismiss).
 * - ``window.confirmationPoll(intervalMs)``: cheap setInterval that
 *   fires ``cartUpdated`` on the body every ``intervalMs`` (default
 *   30s). Rendered only when the cart has lines in "awaiting
 *   confirmation" so the transition to "ready" shows up without user
 *   interaction.
 */
(function () {
  "use strict";

  var STORAGE_KEY = "shopman.confirmation.announced";

  function readAnnounced() {
    try {
      var raw = window.sessionStorage.getItem(STORAGE_KEY);
      return raw ? JSON.parse(raw) : {};
    } catch (_e) {
      return {};
    }
  }

  function writeAnnounced(map) {
    try {
      window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(map));
    } catch (_e) {
      /* storage may be disabled — safe to drop */
    }
  }

  window.confirmationCountdown = function (deadlineIso, deadlineDisplay) {
    return {
      deadlineLabel: deadlineDisplay || "",
      countdownLabel: "",
      _timer: null,
      init: function () {
        var deadline = new Date(deadlineIso);
        if (isNaN(deadline.getTime())) {
          this.countdownLabel = "";
          return;
        }
        var self = this;
        this.tick(deadline);
        this._timer = window.setInterval(function () {
          self.tick(deadline);
        }, 1000);
      },
      tick: function (deadline) {
        var ms = deadline - new Date();
        if (ms <= 0) {
          this.countdownLabel = "expirado";
          if (this._timer) {
            window.clearInterval(this._timer);
            this._timer = null;
          }
          if (window.htmx) {
            window.htmx.trigger(document.body, "cartUpdated");
          }
          return;
        }
        var totalSec = Math.floor(ms / 1000);
        var min = Math.floor(totalSec / 60);
        var sec = totalSec % 60;
        this.countdownLabel =
          min + "m " + (sec < 10 ? "0" + sec : sec) + "s";
      },
      destroy: function () {
        if (this._timer) {
          window.clearInterval(this._timer);
          this._timer = null;
        }
      },
    };
  };

  window.confirmationPoll = function (intervalMs) {
    return {
      _timer: null,
      init: function () {
        var ms = intervalMs > 0 ? intervalMs : 30000;
        this._timer = window.setInterval(function () {
          if (window.htmx) {
            window.htmx.trigger(document.body, "cartUpdated");
          }
        }, ms);
      },
      destroy: function () {
        if (this._timer) {
          window.clearInterval(this._timer);
          this._timer = null;
        }
      },
    };
  };

  window.confirmationReadyAnnounce = function (lineId, itemName, deadlineDisplay) {
    return {
      init: function () {
        if (!lineId) return;
        var seen = readAnnounced();
        if (seen[lineId]) return;
        seen[lineId] = true;
        writeAnnounced(seen);
        var msg = "Tudo pronto! " + itemName;
        if (deadlineDisplay) {
          msg += " — confirme até " + deadlineDisplay + ".";
        } else {
          msg += ".";
        }
        // ``sticky: true`` — the toast stays on screen until the shopper
        // clicks dismiss. Arrival is a must-see event (omotenashi +
        // transparent timeouts) so auto-dismiss is not acceptable here.
        //
        // ``setTimeout(..., 0)`` defers the dispatch to the next task so
        // the toast-stack's ``x-on:notify.window`` listener is already
        // bound by the time the event fires. Without the defer, Alpine's
        // initialization order can leave the listener unregistered when
        // init() runs.
        window.setTimeout(function () {
          window.dispatchEvent(
            new CustomEvent("notify", {
              detail: { variant: "success", message: msg, sticky: true },
            })
          );
        }, 0);
      },
    };
  };
})();
