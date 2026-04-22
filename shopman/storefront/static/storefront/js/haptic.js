/*
 * Haptic feedback helper for storefront.
 *
 * Exposes window.triggerHaptic(pattern) as a thin wrapper around
 * navigator.vibrate. Browsers without vibrate support (Safari desktop,
 * some iOS webviews) silently no-op.
 *
 * Semantic patterns chosen for common UX moments — use by name to keep
 * feedback intensity consistent across the app:
 *
 *   triggerHaptic.light()   — single short tap (10ms)       add-to-cart
 *   triggerHaptic.double()  — two short taps                  remove-from-cart
 *   triggerHaptic.confirm() — triple tap                      order-commit
 *   triggerHaptic.error()   — single firm tap (100ms)         validation error
 *
 * Also accepts a raw pattern: triggerHaptic(20) or triggerHaptic([30, 20, 30]).
 */
(function () {
  'use strict';

  function vibrate(pattern) {
    if (typeof navigator === 'undefined' || !navigator.vibrate) return false;
    try {
      return navigator.vibrate(pattern);
    } catch (err) {
      return false;
    }
  }

  function triggerHaptic(pattern) {
    if (pattern === undefined) pattern = 10;
    return vibrate(pattern);
  }

  triggerHaptic.light   = function () { return vibrate(10); };
  triggerHaptic.double  = function () { return vibrate([30, 20, 30]); };
  triggerHaptic.confirm = function () { return vibrate([50, 30, 50]); };
  triggerHaptic.error   = function () { return vibrate(100); };

  window.triggerHaptic = triggerHaptic;
})();
