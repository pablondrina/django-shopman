/**
 * Proto Scenarios — Painel de cenários para protótipos Nelson Boulangerie
 *
 * Include this script in any proto page to get a collapsible scenario panel.
 * It overrides Alpine reactive data to simulate different user contexts.
 * State persists across pages via sessionStorage.
 *
 * Usage: Add before closing </body>:
 *   <script src="proto-scenarios.js"></script>
 */

const STORAGE_KEY = 'proto_scenario_state';

document.addEventListener('alpine:init', () => {
  // ── Scenario Presets ──────────────────────────────────────────────
  const PRESETS = [
    {
      id: 'maria-morning',
      label: 'Maria · Fiel · Manhã · Perto',
      icon: '☀️',
      description: 'Recorrente, 1.2km, 9h — croissants saindo do forno',
      vars: { hour: 9, minute: 0, isReturning: true, userDistance: 1.2, geolocationDenied: false, geolocationLoading: false, locationConfirmed: false, customerName: 'Maria', orderCount: 12, favoriteItem: 'Croissant Clássico', closingHour: 19 }
    },
    {
      id: 'maria-early',
      label: 'Maria · Fiel · Cedinho · Antes de Abrir',
      icon: '🌅',
      description: 'Recorrente, 0.8km, 6h30 — loja ainda fechada',
      vars: { hour: 6, minute: 30, isReturning: true, userDistance: 0.8, geolocationDenied: false, geolocationLoading: false, locationConfirmed: false, customerName: 'Maria', orderCount: 12, favoriteItem: 'Croissant Clássico', closingHour: 19 }
    },
    {
      id: 'lunch-rush',
      label: 'Carlos · Fiel · Almoço · Perto',
      icon: '🥪',
      description: 'Recorrente, 0.5km, 12h — hora do almoço rápido',
      vars: { hour: 12, minute: 0, isReturning: true, userDistance: 0.5, geolocationDenied: false, geolocationLoading: false, locationConfirmed: false, customerName: 'Carlos', orderCount: 8, favoriteItem: 'Sanduíche Natural', closingHour: 19 }
    },
    {
      id: 'maria-night',
      label: 'Maria · Fiel · Noite · Fechado',
      icon: '🌙',
      description: 'Recorrente, 1.2km, 20h — loja fechada',
      vars: { hour: 20, minute: 0, isReturning: true, userDistance: 1.2, geolocationDenied: false, geolocationLoading: false, locationConfirmed: false, customerName: 'Maria', orderCount: 12, favoriteItem: 'Croissant Clássico', closingHour: 19 }
    },
    {
      id: 'joao-near',
      label: 'João · Novo · Manhã · Perto',
      icon: '🆕',
      description: 'Primeiro acesso, 2km, 10h',
      vars: { hour: 10, minute: 0, isReturning: false, userDistance: 2.0, geolocationDenied: false, geolocationLoading: false, locationConfirmed: false, customerName: 'João', orderCount: 0, favoriteItem: '', closingHour: 19 }
    },
    {
      id: 'joao-marginal',
      label: 'João · Novo · Zona Marginal',
      icon: '⚠️',
      description: 'Primeiro acesso, 6km, 14h',
      vars: { hour: 14, minute: 0, isReturning: false, userDistance: 6.0, geolocationDenied: false, geolocationLoading: false, locationConfirmed: false, customerName: 'João', orderCount: 0, favoriteItem: '', closingHour: 19 }
    },
    {
      id: 'ana-outside',
      label: 'Ana · Nova · Fora do Raio',
      icon: '📍',
      description: 'Primeiro acesso, 9km, 11h',
      vars: { hour: 11, minute: 0, isReturning: false, userDistance: 9.0, geolocationDenied: false, geolocationLoading: false, locationConfirmed: false, customerName: 'Ana', orderCount: 0, favoriteItem: '', closingHour: 19 }
    },
    {
      id: 'pedro-denied',
      label: 'Pedro · Geo Negada',
      icon: '🚫',
      description: 'Localização bloqueada, 15h',
      vars: { hour: 15, minute: 0, isReturning: false, userDistance: null, geolocationDenied: true, geolocationLoading: false, locationConfirmed: false, customerName: 'Pedro', orderCount: 0, favoriteItem: '', closingHour: 19 }
    },
    {
      id: 'happyhour',
      label: 'Happy Hour · Fiel · Perto',
      icon: '🍻',
      description: 'Recorrente, 0.8km, 16h — descontos ativos',
      vars: { hour: 16, minute: 0, isReturning: true, userDistance: 0.8, geolocationDenied: false, geolocationLoading: false, locationConfirmed: false, customerName: 'Maria', orderCount: 15, favoriteItem: 'Croissant Clássico', closingHour: 19 }
    },
    {
      id: 'closing-soon',
      label: 'Fechando · Novo · Perto',
      icon: '⏰',
      description: 'Novo, 1.5km, 18h — últimos pedidos',
      vars: { hour: 18, minute: 30, isReturning: false, userDistance: 1.5, geolocationDenied: false, geolocationLoading: false, locationConfirmed: false, customerName: 'Lucas', orderCount: 0, favoriteItem: '', closingHour: 19 }
    }
  ];

  // ── Persistence helpers ───────────────────────────────────────────
  function saveState(state) {
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch (e) {}
  }

  function loadState() {
    try {
      const raw = sessionStorage.getItem(STORAGE_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch (e) {
      return null;
    }
  }

  // ── Panel Component ───────────────────────────────────────────────
  Alpine.data('protoScenarios', () => {
    const saved = loadState();

    return {
      open: false,
      tab: saved?.tab || 'presets',
      activePreset: saved?.activePreset || null,
      currentPage: detectCurrentPage(),
      initialized: false,

      // Granular controls (mirrors reactive vars)
      ctrl: saved?.ctrl || {
        hour: new Date().getHours(),
        isReturning: true,
        userDistance: 1.2,
        geolocationDenied: false,
        locationConfirmed: false,
        customerName: 'Maria',
        orderCount: 12,
        favoriteItem: 'Croissant Clássico',
        closingHour: 19,
        fulfillmentMode: 'pickup',
        cartEmpty: false,
        checkoutStep: 1,
      },

      presets: PRESETS,

      init() {
        // Auto-apply saved state on page load
        if (saved) {
          this.$nextTick(() => {
            if (saved.activePreset) {
              const preset = PRESETS.find(p => p.id === saved.activePreset);
              if (preset) {
                this.pushToPage(preset.vars);
              }
            } else {
              // Manual controls mode — reconstruct vars from ctrl
              this.pushControlsToPage();
            }
            this.initialized = true;
          });
        } else {
          this.initialized = true;
        }
      },

      persist() {
        saveState({
          tab: this.tab,
          activePreset: this.activePreset,
          ctrl: { ...this.ctrl }
        });
      },

      toggle() {
        this.open = !this.open;
        if (navigator.vibrate) navigator.vibrate(10);
      },

      applyPreset(preset) {
        this.activePreset = preset.id;
        // Update controls to match preset vars
        Object.keys(preset.vars).forEach(k => {
          if (k in this.ctrl) this.ctrl[k] = preset.vars[k];
        });
        this.pushToPage(preset.vars);
        this.persist();
        if (navigator.vibrate) navigator.vibrate([10, 30, 10]);
      },

      applyControls() {
        this.activePreset = null;
        this.pushControlsToPage();
        this.persist();
      },

      pushControlsToPage() {
        const vars = {
          hour: this.ctrl.hour,
          minute: 0,
          isReturning: this.ctrl.isReturning,
          userDistance: this.ctrl.geolocationDenied ? null : this.ctrl.userDistance,
          geolocationDenied: this.ctrl.geolocationDenied,
          geolocationLoading: false,
          locationConfirmed: this.ctrl.locationConfirmed,
          customerName: this.ctrl.customerName,
          orderCount: this.ctrl.orderCount,
          favoriteItem: this.ctrl.favoriteItem,
          closingHour: this.ctrl.closingHour,
        };
        this.pushToPage(vars);
      },

      pushToPage(vars) {
        // Find the root Alpine component (body or first x-data element)
        const targets = document.querySelectorAll('[x-data]');
        let pageRoot = null;
        for (const el of targets) {
          // Skip our own panel
          if (el._x_dataStack && el._x_dataStack[0] && 'presets' in el._x_dataStack[0]) continue;
          pageRoot = el;
          break;
        }

        if (!pageRoot || !pageRoot._x_dataStack) return;

        const data = pageRoot._x_dataStack[0];

        // Apply common vars
        Object.keys(vars).forEach(k => {
          if (k in data) data[k] = vars[k];
        });

        // Recalculate deliveryMinutes if distance changed
        if ('userDistance' in vars && vars.userDistance !== null) {
          if ('deliveryMinutes' in data) {
            data.deliveryMinutes = Math.max(15, Math.ceil(vars.userDistance * 8) + 10);
          }
        }

        // Update sessionStorage for cross-page geo consistency
        if (vars.userDistance !== null && vars.userDistance !== undefined) {
          const zone = vars.userDistance <= 5 ? 'within' : vars.userDistance <= 7 ? 'marginal' : 'outside';
          sessionStorage.setItem('shopman_geo', JSON.stringify({
            distance: vars.userDistance,
            zone: zone,
            accuracy: 50
          }));
        }

        // Cart-specific
        if (this.ctrl.fulfillmentMode && 'fulfillmentMode' in data) {
          data.fulfillmentMode = this.ctrl.fulfillmentMode;
        }
        if (this.ctrl.cartEmpty && 'items' in data) {
          data.items = [];
        }

        // Checkout-specific
        if ('step' in data && this.ctrl.checkoutStep) {
          data.step = this.ctrl.checkoutStep;
        }
      },

      resetScenario() {
        sessionStorage.removeItem(STORAGE_KEY);
        sessionStorage.removeItem('shopman_geo');
        sessionStorage.removeItem('shopman_fulfillment');
        this.activePreset = null;
        this.ctrl = {
          hour: new Date().getHours(),
          isReturning: true,
          userDistance: 1.2,
          geolocationDenied: false,
          locationConfirmed: false,
          customerName: 'Maria',
          orderCount: 12,
          favoriteItem: 'Croissant Clássico',
          closingHour: 19,
          fulfillmentMode: 'pickup',
          cartEmpty: false,
          checkoutStep: 1,
        };
        // Reload to get fresh page state
        window.location.reload();
      },

      getTimeLabel(h) {
        if (h < 7) return `${h}h · Madrugada`;
        if (h < 12) return `${h}h · Manhã`;
        if (h < 14) return `${h}h · Almoço`;
        if (h < 18) return `${h}h · Tarde`;
        if (h < 19) return `${h}h · Fim do dia`;
        return `${h}h · Noite`;
      },

      getDistanceLabel(d) {
        if (d <= 5) return `${d} km · Dentro do raio`;
        if (d <= 7) return `${d} km · Zona marginal`;
        return `${d} km · Fora do raio`;
      },

      getDistanceColor(d) {
        if (d <= 5) return '#059669';
        if (d <= 7) return '#d97706';
        return '#6b7280';
      },

      isRelevantControl(name) {
        const page = this.currentPage;
        const cartOnly = ['fulfillmentMode', 'cartEmpty'];
        const checkoutOnly = ['checkoutStep'];

        if (cartOnly.includes(name)) return page === 'cart';
        if (checkoutOnly.includes(name)) return page === 'checkout';
        return true; // Common controls always visible
      }
    };
  });
});

function detectCurrentPage() {
  const path = window.location.pathname;
  const file = path.split('/').pop().replace('.html', '');
  return file || 'home';
}

// ── Inject Panel HTML ───────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const panel = document.createElement('div');
  panel.setAttribute('x-data', 'protoScenarios');
  panel.setAttribute('x-cloak', '');
  panel.innerHTML = `
    <!-- Toggle Button -->
    <button @click="toggle()"
            :class="[
              open ? 'bg-violet-600' : activePreset ? 'bg-violet-500' : 'bg-neutral-800'
            ]"
            class="fixed z-[9999] flex items-center justify-center w-10 h-10 rounded-full
                   text-white shadow-lg transition-all active:scale-95 hover:shadow-xl"
            style="top: calc(0.75rem + env(safe-area-inset-top, 0px)); left: 0.75rem;">
      <span class="material-symbols-rounded text-[20px]" x-text="open ? 'close' : 'science'"></span>
    </button>

    <!-- Active scenario indicator (when panel closed) -->
    <div x-show="!open && activePreset"
         x-transition
         class="fixed z-[9998] pointer-events-none"
         style="top: calc(3rem + env(safe-area-inset-top, 0px)); left: 0.75rem;">
      <span class="text-[9px] font-bold text-violet-500 bg-white/90 px-1.5 py-0.5 rounded shadow-sm border border-violet-200"
            x-text="presets.find(p => p.id === activePreset)?.label?.split(' · ')[0] || ''"></span>
    </div>

    <!-- Panel -->
    <div x-show="open"
         x-transition:enter="transition ease-out duration-200"
         x-transition:enter-start="opacity-0 -translate-y-2"
         x-transition:enter-end="opacity-100 translate-y-0"
         x-transition:leave="transition ease-in duration-150"
         x-transition:leave-start="opacity-100 translate-y-0"
         x-transition:leave-end="opacity-0 -translate-y-2"
         class="fixed z-[9998] bg-white rounded-lg shadow-2xl border border-neutral-200 overflow-hidden"
         style="top: calc(3.5rem + env(safe-area-inset-top, 0px)); left: 0.75rem; right: 0.75rem; max-width: 360px; max-height: calc(100vh - 5rem);">

      <!-- Panel Header -->
      <div class="px-3 pt-3 pb-2 border-b border-neutral-100">
        <div class="flex items-center justify-between mb-2">
          <p class="text-xs font-bold text-violet-600 uppercase tracking-wider">Proto Cenários</p>
          <div class="flex items-center gap-2">
            <p class="text-[10px] text-neutral-400 font-mono" x-text="currentPage + '.html'"></p>
            <button @click="resetScenario()" class="text-[9px] text-red-400 hover:text-red-600 font-medium uppercase tracking-wider transition-colors">Reset</button>
          </div>
        </div>

        <!-- Tabs -->
        <div class="flex gap-1">
          <button @click="tab = 'presets'; persist()"
                  :class="tab === 'presets' ? 'bg-neutral-900 text-white' : 'bg-neutral-100 text-neutral-600'"
                  class="flex-1 text-[11px] font-semibold py-1.5 rounded-md transition-colors">
            Personas
          </button>
          <button @click="tab = 'controls'; persist()"
                  :class="tab === 'controls' ? 'bg-neutral-900 text-white' : 'bg-neutral-100 text-neutral-600'"
                  class="flex-1 text-[11px] font-semibold py-1.5 rounded-md transition-colors">
            Controles
          </button>
        </div>
      </div>

      <!-- Panel Content (scrollable) -->
      <div class="overflow-y-auto" style="max-height: calc(100vh - 12rem);">

        <!-- Presets Tab -->
        <div x-show="tab === 'presets'" class="p-2 space-y-1">
          <template x-for="preset in presets" :key="preset.id">
            <button @click="applyPreset(preset)"
                    :class="activePreset === preset.id
                      ? 'bg-violet-50 border-violet-300 ring-1 ring-violet-200'
                      : 'bg-white border-neutral-200 hover:bg-neutral-50'"
                    class="w-full flex items-start gap-2.5 px-3 py-2.5 rounded-lg border text-left transition-all active:scale-[0.98]">
              <span class="text-base mt-0.5 shrink-0" x-text="preset.icon"></span>
              <div class="flex-1 min-w-0">
                <p class="text-xs font-semibold text-neutral-900" x-text="preset.label"></p>
                <p class="text-[10px] text-neutral-500 mt-0.5" x-text="preset.description"></p>
              </div>
              <span x-show="activePreset === preset.id" class="material-symbols-rounded text-[16px] text-violet-600 mt-0.5 shrink-0">check_circle</span>
            </button>
          </template>
        </div>

        <!-- Controls Tab -->
        <div x-show="tab === 'controls'" class="p-3 space-y-4">

          <!-- Hora -->
          <div x-show="isRelevantControl('hour')">
            <div class="flex items-center justify-between mb-1.5">
              <label class="text-[11px] font-semibold text-neutral-700 uppercase tracking-wider">Hora do dia</label>
              <span class="text-[11px] font-mono px-1.5 py-0.5 rounded bg-neutral-100 text-neutral-600" x-text="getTimeLabel(ctrl.hour)"></span>
            </div>
            <input type="range" min="0" max="23" step="1"
                   x-model.number="ctrl.hour"
                   @input="applyControls()"
                   class="w-full h-1.5 bg-neutral-200 rounded-full appearance-none cursor-pointer accent-violet-600">
            <div class="flex justify-between text-[9px] text-neutral-400 mt-0.5">
              <span>0h</span><span>6h</span><span>12h</span><span>18h</span><span>23h</span>
            </div>
          </div>

          <!-- Distância -->
          <div x-show="isRelevantControl('userDistance') && !ctrl.geolocationDenied">
            <div class="flex items-center justify-between mb-1.5">
              <label class="text-[11px] font-semibold text-neutral-700 uppercase tracking-wider">Distância</label>
              <span class="text-[11px] font-mono px-1.5 py-0.5 rounded text-white"
                    :style="'background:' + getDistanceColor(ctrl.userDistance)"
                    x-text="getDistanceLabel(ctrl.userDistance)"></span>
            </div>
            <input type="range" min="0.5" max="15" step="0.5"
                   x-model.number="ctrl.userDistance"
                   @input="applyControls()"
                   class="w-full h-1.5 bg-neutral-200 rounded-full appearance-none cursor-pointer accent-violet-600">
            <div class="flex justify-between text-[9px] text-neutral-400 mt-0.5">
              <span>0.5km</span>
              <span class="text-emerald-500 font-semibold">|5km</span>
              <span class="text-amber-500 font-semibold">|7km</span>
              <span>15km</span>
            </div>
          </div>

          <!-- Geolocation denied -->
          <div x-show="isRelevantControl('geolocationDenied')" class="flex items-center justify-between">
            <label class="text-[11px] font-semibold text-neutral-700 uppercase tracking-wider">Geo negada</label>
            <button @click="ctrl.geolocationDenied = !ctrl.geolocationDenied; applyControls()"
                    :class="ctrl.geolocationDenied ? 'bg-red-500' : 'bg-neutral-300'"
                    class="relative w-9 h-5 rounded-full transition-colors">
              <span :class="ctrl.geolocationDenied ? 'translate-x-4' : 'translate-x-0.5'"
                    class="absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform"></span>
            </button>
          </div>

          <!-- Location confirmed -->
          <div x-show="isRelevantControl('locationConfirmed') && !ctrl.geolocationDenied" class="flex items-center justify-between">
            <label class="text-[11px] font-semibold text-neutral-700 uppercase tracking-wider">Loc. confirmada</label>
            <button @click="ctrl.locationConfirmed = !ctrl.locationConfirmed; applyControls()"
                    :class="ctrl.locationConfirmed ? 'bg-emerald-500' : 'bg-neutral-300'"
                    class="relative w-9 h-5 rounded-full transition-colors">
              <span :class="ctrl.locationConfirmed ? 'translate-x-4' : 'translate-x-0.5'"
                    class="absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform"></span>
            </button>
          </div>

          <!-- Returning customer -->
          <div x-show="isRelevantControl('isReturning')" class="flex items-center justify-between">
            <label class="text-[11px] font-semibold text-neutral-700 uppercase tracking-wider">Cliente recorrente</label>
            <button @click="ctrl.isReturning = !ctrl.isReturning; applyControls()"
                    :class="ctrl.isReturning ? 'bg-violet-500' : 'bg-neutral-300'"
                    class="relative w-9 h-5 rounded-full transition-colors">
              <span :class="ctrl.isReturning ? 'translate-x-4' : 'translate-x-0.5'"
                    class="absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform"></span>
            </button>
          </div>

          <!-- Customer name -->
          <div x-show="isRelevantControl('customerName')">
            <label class="text-[11px] font-semibold text-neutral-700 uppercase tracking-wider mb-1.5 block">Nome do cliente</label>
            <input type="text"
                   x-model="ctrl.customerName"
                   @input="applyControls()"
                   placeholder="ex: Maria"
                   class="w-full px-3 py-2 text-[12px] rounded-lg border border-neutral-200 bg-white focus:outline-none focus:border-violet-400">
          </div>

          <!-- Order count -->
          <div x-show="isRelevantControl('orderCount')">
            <div class="flex items-center justify-between mb-1.5">
              <label class="text-[11px] font-semibold text-neutral-700 uppercase tracking-wider">Contagem de pedidos</label>
              <span class="text-[11px] font-mono px-1.5 py-0.5 rounded bg-neutral-100 text-neutral-600" x-text="ctrl.orderCount"></span>
            </div>
            <input type="range" min="0" max="50" step="1"
                   x-model.number="ctrl.orderCount"
                   @input="applyControls()"
                   class="w-full h-1.5 bg-neutral-200 rounded-full appearance-none cursor-pointer accent-violet-600">
            <div class="flex justify-between text-[9px] text-neutral-400 mt-0.5">
              <span>0</span><span>25</span><span>50</span>
            </div>
          </div>

          <!-- Divider for page-specific controls -->
          <template x-if="currentPage === 'cart' || currentPage === 'checkout'">
            <div class="border-t border-neutral-200 pt-3">
              <p class="text-[10px] font-bold text-neutral-400 uppercase tracking-wider mb-3" x-text="currentPage === 'cart' ? 'Carrinho' : 'Checkout'"></p>
            </div>
          </template>

          <!-- Fulfillment mode (cart) -->
          <div x-show="isRelevantControl('fulfillmentMode')">
            <label class="text-[11px] font-semibold text-neutral-700 uppercase tracking-wider mb-1.5 block">Modo</label>
            <div class="flex gap-1">
              <button @click="ctrl.fulfillmentMode = 'pickup'; applyControls()"
                      :class="ctrl.fulfillmentMode === 'pickup' ? 'bg-neutral-900 text-white' : 'bg-neutral-100 text-neutral-600'"
                      class="flex-1 text-[11px] font-semibold py-1.5 rounded-md transition-colors">
                Retirar
              </button>
              <button @click="ctrl.fulfillmentMode = 'delivery'; applyControls()"
                      :class="ctrl.fulfillmentMode === 'delivery' ? 'bg-neutral-900 text-white' : 'bg-neutral-100 text-neutral-600'"
                      class="flex-1 text-[11px] font-semibold py-1.5 rounded-md transition-colors">
                Entregar
              </button>
            </div>
          </div>

          <!-- Empty cart toggle -->
          <div x-show="isRelevantControl('cartEmpty')" class="flex items-center justify-between">
            <label class="text-[11px] font-semibold text-neutral-700 uppercase tracking-wider">Carrinho vazio</label>
            <button @click="ctrl.cartEmpty = !ctrl.cartEmpty; applyControls()"
                    :class="ctrl.cartEmpty ? 'bg-red-500' : 'bg-neutral-300'"
                    class="relative w-9 h-5 rounded-full transition-colors">
              <span :class="ctrl.cartEmpty ? 'translate-x-4' : 'translate-x-0.5'"
                    class="absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform"></span>
            </button>
          </div>

          <!-- Checkout step -->
          <div x-show="isRelevantControl('checkoutStep')">
            <div class="flex items-center justify-between mb-1.5">
              <label class="text-[11px] font-semibold text-neutral-700 uppercase tracking-wider">Step do checkout</label>
              <span class="text-[11px] font-mono px-1.5 py-0.5 rounded bg-neutral-100 text-neutral-600" x-text="ctrl.checkoutStep + '/4'"></span>
            </div>
            <div class="flex gap-1">
              <template x-for="s in [1,2,3,4]" :key="s">
                <button @click="ctrl.checkoutStep = s; applyControls()"
                        :class="ctrl.checkoutStep === s ? 'bg-neutral-900 text-white' : 'bg-neutral-100 text-neutral-600'"
                        class="flex-1 text-[11px] font-semibold py-1.5 rounded-md transition-colors"
                        x-text="s"></button>
              </template>
            </div>
          </div>

          <!-- Apply button -->
          <button @click="applyControls()"
                  class="w-full mt-2 py-2 rounded-lg bg-violet-600 text-white text-xs font-semibold
                         transition-all active:scale-[0.98] hover:bg-violet-700">
            Aplicar Controles
          </button>

        </div>
      </div>

      <!-- Panel Footer -->
      <div class="px-3 py-2 border-t border-neutral-100 bg-neutral-50">
        <p class="text-[9px] text-neutral-400 text-center">Proto Scenarios · Nelson Boulangerie · Omotenashi-first</p>
      </div>
    </div>
  `;
  document.body.appendChild(panel);
});
