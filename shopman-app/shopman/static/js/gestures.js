/**
 * Gestures — swipe and touch interactions
 *
 * Swipe right (edge) → navigate back
 * Swipe down on bottom sheets / focus overlay → close
 * Pull-to-refresh on tracking / orders → HTMX refresh
 */
(function() {
  'use strict';

  var EDGE_THRESHOLD = 30;   // px from left edge to start swipe
  var SWIPE_THRESHOLD = 80;  // px minimum distance for swipe back
  var SWIPE_VELOCITY = 0.3;  // px/ms minimum velocity

  var startX = 0;
  var startY = 0;
  var startTime = 0;
  var isEdgeSwipe = false;
  var isPullRefresh = false;

  // ── Swipe Back (edge gesture) ──

  document.addEventListener('touchstart', function(e) {
    var touch = e.touches[0];
    startX = touch.clientX;
    startY = touch.clientY;
    startTime = Date.now();
    isEdgeSwipe = startX < EDGE_THRESHOLD;
    isPullRefresh = false;
  }, { passive: true });

  document.addEventListener('touchend', function(e) {
    if (!isEdgeSwipe && !isPullRefresh) return;

    var touch = e.changedTouches[0];
    var deltaX = touch.clientX - startX;
    var deltaY = touch.clientY - startY;
    var elapsed = Date.now() - startTime;

    // Swipe right from edge → back
    if (isEdgeSwipe && deltaX > SWIPE_THRESHOLD && Math.abs(deltaY) < deltaX * 0.5) {
      var velocity = deltaX / elapsed;
      if (velocity > SWIPE_VELOCITY) {
        e.preventDefault();
        window.history.back();
      }
    }

    // Pull-to-refresh: handled separately
    isEdgeSwipe = false;
    isPullRefresh = false;
  }, { passive: false });


  // ── Pull-to-Refresh ──
  // Only on pages with [data-pull-refresh] attribute
  // Triggers HTMX refresh on the marked element

  var pullStartY = 0;
  var pullElement = null;
  var PULL_THRESHOLD = 60;

  document.addEventListener('touchstart', function(e) {
    var el = document.querySelector('[data-pull-refresh]');
    if (!el) return;
    // Only trigger if at top of scroll
    if (window.scrollY > 0) return;
    pullStartY = e.touches[0].clientY;
    pullElement = el;
  }, { passive: true });

  document.addEventListener('touchend', function(e) {
    if (!pullElement) return;
    var deltaY = e.changedTouches[0].clientY - pullStartY;
    if (deltaY > PULL_THRESHOLD && window.scrollY === 0) {
      // Trigger HTMX refresh
      if (typeof htmx !== 'undefined') {
        htmx.trigger(pullElement, 'pull-refresh');
      }
    }
    pullElement = null;
  }, { passive: true });


  // ── Swipe Down to Close ──
  // Bottom sheets and focus overlay: close on swipe down

  document.addEventListener('touchstart', function(e) {
    var target = e.target.closest('[data-swipe-dismiss]');
    if (!target) return;
    startY = e.touches[0].clientY;
  }, { passive: true });

  document.addEventListener('touchend', function(e) {
    var target = e.target.closest('[data-swipe-dismiss]');
    if (!target) return;
    var deltaY = e.changedTouches[0].clientY - startY;
    if (deltaY > 60) {
      // Dispatch close event
      window.dispatchEvent(new CustomEvent('close-focus'));
      // Also try Alpine dismiss
      var closeBtn = target.querySelector('[data-dismiss]');
      if (closeBtn) closeBtn.click();
    }
  }, { passive: true });

})();
