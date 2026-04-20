/* Address picker Alpine component — iFood-style.
 *
 * Depends on:
 *   - Alpine.js (base template)
 *   - Google Maps JS API (loaded by the partial when present)
 *
 * The component exposes `addressPicker(config)` as a factory. `config`:
 *   {
 *     initialAddresses: Array<{id, label, route, street_number, complement,
 *                               neighborhood, city, state_code, postal_code,
 *                               latitude, longitude, place_id,
 *                               formatted_address, delivery_instructions,
 *                               is_default}>,
 *     preselectedId: number|null,
 *     shopLocation: {lat, lng}|null,
 *     cepLookupUrl: string,
 *     reverseGeocodeUrl: string,
 *     csrfToken: string,
 *     mode: "checkout" | "account",
 *   }
 */
(function (global) {
  "use strict";

  // ── helpers ──────────────────────────────────────────────────────────────

  const onlyDigits = (s) => String(s || "").replace(/\D+/g, "");

  const formatCep = (s) => {
    const d = onlyDigits(s).slice(0, 8);
    return d.length > 5 ? d.slice(0, 5) + "-" + d.slice(5) : d;
  };

  const looksLikeCep = (s) => onlyDigits(s).length === 8;

  const fieldFromComponents = (components, ...types) => {
    const want = new Set(types);
    for (const c of components || []) {
      if ((c.types || []).some((t) => want.has(t))) return c.long_name || "";
    }
    return "";
  };

  const fieldFromComponentsShort = (components, ...types) => {
    const want = new Set(types);
    for (const c of components || []) {
      if ((c.types || []).some((t) => want.has(t))) return c.short_name || "";
    }
    return "";
  };

  // ── factory ──────────────────────────────────────────────────────────────

  global.addressPicker = function addressPicker(config) {
    const cfg = Object.assign(
      {
        initialAddresses: [],
        preselectedId: null,
        initialDraft: null,
        shopLocation: null,
        cepLookupUrl: "",
        reverseGeocodeUrl: "",
        csrfToken: "",
        mode: "checkout",
      },
      config || {},
    );

    return {
      // ── State ──────────────────────────────────────────────────────────
      mode: cfg.mode,
      addresses: Array.isArray(cfg.initialAddresses) ? cfg.initialAddresses : [],
      selectedId: cfg.preselectedId == null ? null : Number(cfg.preselectedId),

      /** "new" when editing a brand-new address; otherwise "saved". */
      view: "saved",

      search: "",
      searching: false,
      searchError: "",

      /* Address fields being composed. */
      draft: {
        route: "",
        street_number: "",
        complement: "",
        neighborhood: "",
        city: "",
        state_code: "",
        postal_code: "",
        latitude: null,
        longitude: null,
        place_id: "",
        formatted_address: "",
        delivery_instructions: "",
        is_verified: false,
      },

      /* UI flags. */
      showMap: false,
      map: null,
      marker: null,
      mapLoaded: false,

      showLabelModal: false,
      justSavedId: null,
      labelDraft: "home",
      labelCustom: "",

      busy: false,
      toast: "",

      // ── Computed ───────────────────────────────────────────────────────
      get selected() {
        if (this.selectedId == null) return null;
        return this.addresses.find((a) => Number(a.id) === Number(this.selectedId)) || null;
      },
      get hasSaved() {
        return this.addresses.length > 0;
      },
      get readyToPick() {
        // Enough data to call the address usable.
        const d = this.draft;
        return Boolean((d.route || d.formatted_address) && d.street_number);
      },

      // ── Lifecycle ──────────────────────────────────────────────────────
      init() {
        // Hydrate from server-side draft on error re-render. Keeps what the
        // customer typed and opens straight into the new-address form so the
        // error message has an obvious place to act on.
        if (cfg.initialDraft && typeof cfg.initialDraft === "object") {
          Object.assign(this.draft, cfg.initialDraft);
          this.search = this.draft.formatted_address || "";
          this.view = "new";
          this.selectedId = null;
          return;
        }
        // If a preselected address is present, stick to saved.
        // Otherwise, if there are no saved addresses at all, jump to "new".
        if (this.hasSaved && this.selectedId != null) {
          this.view = "saved";
        } else if (!this.hasSaved) {
          this.view = "new";
        }
      },

      // ── Saved address selection ────────────────────────────────────────
      selectSaved(id) {
        this.selectedId = Number(id);
        this.view = "saved";
      },
      startNew() {
        this.selectedId = null;
        this.view = "new";
        this.search = "";
        this.resetDraft();
        // Defer focus so x-show transition completes first. Also re-attempt
        // the Autocomplete mount — x-init may have fired before Google
        // Maps finished loading, leaving the input without autocomplete.
        setTimeout(() => {
          const input = this.$refs && this.$refs.searchInput;
          if (input) {
            this.mountAutocomplete(input);
            if (typeof input.focus === "function") input.focus();
          }
        }, 50);
      },
      resetDraft() {
        this.draft = {
          route: "",
          street_number: "",
          complement: "",
          neighborhood: "",
          city: "",
          state_code: "",
          postal_code: "",
          latitude: null,
          longitude: null,
          place_id: "",
          formatted_address: "",
          delivery_instructions: "",
          is_verified: false,
        };
      },

      // ── Google Places Autocomplete ─────────────────────────────────────
      mountAutocomplete(el) {
        if (el.__acMounted) return;
        // Google Maps script is async+defer — x-init may fire before it loads.
        // Poll until ready (up to 10s), then wire the autocomplete. Capture
        // `this` via self so setTimeout's detached callback still hits the
        // Alpine proxy method.
        const self = this;
        if (!global.google || !global.google.maps || !global.google.maps.places) {
          if (!el.__acWaitStart) el.__acWaitStart = Date.now();
          if (Date.now() - el.__acWaitStart < 10000) {
            setTimeout(function () { self.mountAutocomplete(el); }, 200);
          }
          return;
        }
        const opts = {
          types: ["address"],
          componentRestrictions: { country: "br" },
          fields: [
            "address_components",
            "formatted_address",
            "geometry",
            "place_id",
          ],
        };
        if (cfg.shopLocation && cfg.shopLocation.lat && cfg.shopLocation.lng) {
          const ll = new global.google.maps.LatLng(
            cfg.shopLocation.lat,
            cfg.shopLocation.lng,
          );
          opts.origin = ll;
          opts.bounds = new global.google.maps.Circle({
            center: ll,
            radius: 15000,
          }).getBounds();
        }
        const ac = new global.google.maps.places.Autocomplete(el, opts);
        ac.addListener("place_changed", () => {
          const place = ac.getPlace();
          if (!place) return;
          this.acceptPlace(place);
        });
        el.__acMounted = true;
      },
      acceptPlace(place) {
        const comps = place.address_components || [];
        const loc = place.geometry && place.geometry.location;
        this.draft.route = fieldFromComponents(comps, "route");
        this.draft.street_number = fieldFromComponents(comps, "street_number");
        this.draft.neighborhood = fieldFromComponents(
          comps,
          "sublocality_level_1",
          "sublocality",
          "neighborhood",
        );
        this.draft.city = fieldFromComponents(
          comps,
          "administrative_area_level_2",
          "locality",
        );
        this.draft.state_code = fieldFromComponentsShort(
          comps,
          "administrative_area_level_1",
        );
        this.draft.postal_code = fieldFromComponents(comps, "postal_code");
        this.draft.place_id = place.place_id || "";
        this.draft.formatted_address = place.formatted_address || "";
        this.draft.is_verified = true;
        if (loc) {
          this.draft.latitude = typeof loc.lat === "function" ? loc.lat() : loc.lat;
          this.draft.longitude =
            typeof loc.lng === "function" ? loc.lng() : loc.lng;
        }
        // Smart focus: number → complement; missing number → number.
        // The fields live inside an x-show toggled by draft.route, so we
        // wait for the next animation frame (after x-show flips display)
        // before calling focus(); otherwise the browser scrolls past the
        // hidden element and the caret never lands. Also blur the search
        // input first so iOS doesn't keep the suggestion list pinned.
        const search = this.$refs.searchInput;
        if (search && typeof search.blur === "function") search.blur();
        this.focusNextEditableField();
      },

      // Focus number first if missing, otherwise complement. Uses a double
      // RAF to give x-show / browser layout time to settle on slow devices.
      focusNextEditableField() {
        const target = this.draft.street_number ? "complement" : "street_number";
        const apply = () => {
          const el = this.$refs[target];
          if (!el || typeof el.focus !== "function") return;
          el.focus({ preventScroll: false });
          if (typeof el.scrollIntoView === "function") {
            try { el.scrollIntoView({ behavior: "smooth", block: "center" }); } catch (_) {}
          }
        };
        if (typeof requestAnimationFrame === "function") {
          requestAnimationFrame(() => requestAnimationFrame(apply));
        } else {
          setTimeout(apply, 50);
        }
      },

      // ── Manual search fallback (CEP via ViaCEP proxy) ──────────────────
      onSearchEnter() {
        const raw = this.search.trim();
        if (!raw) return;
        if (looksLikeCep(raw)) {
          this.search = formatCep(raw);
          this.lookupCep();
        }
        // Otherwise: Places Autocomplete already handles selection via its
        // own dropdown; Enter just submits the highlighted result.
      },
      async lookupCep() {
        const cep = onlyDigits(this.search);
        if (cep.length !== 8) return;
        this.searching = true;
        this.searchError = "";
        try {
          const url = cfg.cepLookupUrl + "?cep=" + encodeURIComponent(cep);
          const resp = await fetch(url, {
            headers: { "X-Requested-With": "XMLHttpRequest" },
          });
          if (!resp.ok) throw new Error("cep request failed");
          const html = await resp.text();
          // CepLookupView dispatches 'cep-found' via inline Alpine x-init
          // when successful. Parse the dispatch payload here so we don't
          // depend on injecting HTML back into the page.
          const m = html.match(/\$dispatch\('cep-found',\s*(\{[\s\S]*?\})\)/);
          if (m) {
            try {
              const data = JSON.parse(m[1].replace(/(\w+):/g, '"$1":'));
              this.draft.route = data.route || "";
              this.draft.neighborhood = data.neighborhood || "";
              this.draft.city = data.city || "";
              this.draft.state_code = data.stateCode || "";
              this.draft.postal_code = data.postalCode || "";
              this.draft.formatted_address =
                [this.draft.route, this.draft.neighborhood, this.draft.city]
                  .filter(Boolean)
                  .join(", ") || "";
              this.focusNextEditableField();
            } catch (e) {
              this.searchError = "Não consegui ler o endereço do CEP.";
            }
          } else {
            this.searchError =
              "Não encontrei esse CEP. Digite a rua no campo de busca.";
          }
        } catch (e) {
          this.searchError =
            "Falha ao buscar o CEP. Você pode digitar o endereço direto.";
        } finally {
          this.searching = false;
        }
      },

      // ── Geolocation (opt-in button) ────────────────────────────────────
      async useMyLocation() {
        if (!navigator.geolocation) {
          this.searchError = "Seu navegador não suporta localização.";
          return;
        }
        this.searching = true;
        this.searchError = "";
        try {
          const pos = await new Promise((resolve, reject) => {
            navigator.geolocation.getCurrentPosition(resolve, reject, {
              enableHighAccuracy: true,
              timeout: 10000,
              maximumAge: 60000,
            });
          });
          const lat = pos.coords.latitude;
          const lng = pos.coords.longitude;
          await this.reverseGeocode(lat, lng);
        } catch (e) {
          this.searchError =
            "Não consegui acessar sua localização. Tudo bem — digite o endereço.";
        } finally {
          this.searching = false;
        }
      },

      async reverseGeocode(lat, lng) {
        const resp = await fetch(cfg.reverseGeocodeUrl, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": cfg.csrfToken,
          },
          body: JSON.stringify({ lat, lng }),
        });
        if (!resp.ok) {
          this.searchError = "Não consegui identificar o endereço pelo mapa.";
          return;
        }
        const data = await resp.json();
        this.draft.route = data.route || "";
        this.draft.street_number = data.street_number || "";
        this.draft.neighborhood = data.neighborhood || "";
        this.draft.city = data.city || "";
        this.draft.state_code = data.state_code || "";
        this.draft.postal_code = data.postal_code || "";
        this.draft.place_id = data.place_id || "";
        this.draft.formatted_address = data.formatted_address || "";
        this.draft.latitude = data.latitude;
        this.draft.longitude = data.longitude;
        this.draft.is_verified = true;
        this.focusNextEditableField();
      },

      // ── Map modal ──────────────────────────────────────────────────────
      openMap() {
        if (this.draft.latitude == null || this.draft.longitude == null) {
          // Without a seed location, use shop location or Brazil center.
          const ll = cfg.shopLocation || { lat: -14.235, lng: -51.925 };
          this.draft.latitude = ll.lat;
          this.draft.longitude = ll.lng;
        }
        this.showMap = true;
        this.$nextTick(() => this.mountMap());
      },
      closeMap() {
        this.showMap = false;
      },
      mountMap() {
        if (!global.google || !global.google.maps) return;
        const el = this.$refs.mapEl;
        if (!el) return;
        const center = { lat: this.draft.latitude, lng: this.draft.longitude };
        if (!this.map) {
          this.map = new global.google.maps.Map(el, {
            center,
            zoom: 18,
            disableDefaultUI: true,
            zoomControl: true,
            gestureHandling: "greedy",
          });
          this.marker = new global.google.maps.Marker({
            position: center,
            map: this.map,
            draggable: true,
          });
          this.marker.addListener("dragend", () => {
            const p = this.marker.getPosition();
            this.draft.latitude = p.lat();
            this.draft.longitude = p.lng();
          });
        } else {
          this.map.setCenter(center);
          this.marker.setPosition(center);
        }
        // Google Maps needs a resize after modal transition.
        setTimeout(() => {
          if (global.google && this.map) {
            global.google.maps.event.trigger(this.map, "resize");
            this.map.setCenter(center);
          }
        }, 200);
      },
      async confirmMap() {
        await this.reverseGeocode(this.draft.latitude, this.draft.longitude);
        this.showMap = false;
      },

      // ── Label modal (post-save) ────────────────────────────────────────
      openLabelModal(addressId) {
        this.justSavedId = addressId;
        this.labelDraft = "home";
        this.labelCustom = "";
        this.showLabelModal = true;
      },
      closeLabelModal() {
        this.showLabelModal = false;
        this.justSavedId = null;
      },
      async saveLabel() {
        if (!this.justSavedId) {
          this.closeLabelModal();
          return;
        }
        const fd = new FormData();
        fd.append("label", this.labelDraft);
        if (this.labelDraft === "other") fd.append("label_custom", this.labelCustom);
        fd.append("customer_phone", ""); // view ignores this on update.
        try {
          await fetch("/minha-conta/enderecos/" + this.justSavedId + "/label/", {
            method: "POST",
            headers: {
              "X-CSRFToken": cfg.csrfToken,
              "X-Requested-With": "XMLHttpRequest",
            },
            body: fd,
          });
          const addr = this.addresses.find((a) => a.id === this.justSavedId);
          if (addr) {
            addr.label =
              this.labelDraft === "other"
                ? this.labelCustom
                : this.labelDraft === "work"
                ? "Trabalho"
                : "Casa";
          }
        } catch (e) {
          // Non-critical — the address is saved either way.
        }
        this.closeLabelModal();
      },
    };
  };
})(window);
