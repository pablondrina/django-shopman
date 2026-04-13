/**
 * Autocomplete Autofill — shopman-utils
 *
 * Works with Django admin's Select2 autocomplete widgets.
 * When a source field (with data-autofill attribute) changes via Select2,
 * this script copies values from the Select2 result data into target fields.
 *
 * The data-autofill attribute is a JSON mapping:
 *   { "<target_field_name>": "<json_key_in_select2_data>", ... }
 *
 * The Select2 result object must include the json_key in its data
 * (configured via the model admin's serialize_result method).
 */
(function () {
  "use strict";

  function getInlinePrefix(el) {
    // Extract the inline form prefix from the field name.
    // e.g. "order_items-0-product" → "order_items-0-"
    var name = el.getAttribute("name") || "";
    var lastDash = name.lastIndexOf("-");
    return lastDash >= 0 ? name.substring(0, lastDash + 1) : "";
  }

  function applyAutofill(sourceEl) {
    var raw = sourceEl.getAttribute("data-autofill");
    if (!raw) return;

    var mapping;
    try {
      mapping = JSON.parse(raw);
    } catch (e) {
      return;
    }

    // Get the Select2 instance data for the selected item.
    var $source = window.django && window.django.jQuery
      ? window.django.jQuery(sourceEl)
      : null;
    if (!$source || !$source.data("select2")) return;

    var data = $source.select2("data");
    if (!data || !data.length) return;

    var selected = data[0];
    var prefix = getInlinePrefix(sourceEl);

    Object.keys(mapping).forEach(function (targetField) {
      var jsonKey = mapping[targetField];
      if (!(jsonKey in selected)) return;

      // Find the target input by name within the same inline row.
      var targetName = prefix + targetField;
      var targetEl = document.querySelector(
        '[name="' + targetName + '"]'
      );
      if (targetEl) {
        targetEl.value = selected[jsonKey];
        // Trigger change so Django admin picks up the new value.
        targetEl.dispatchEvent(new Event("change", { bubbles: true }));
      }
    });
  }

  function init() {
    var $ = window.django && window.django.jQuery;
    if (!$) return;

    // Delegate Select2 change events on elements with data-autofill.
    $(document).on("select2:select", "[data-autofill]", function () {
      applyAutofill(this);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
