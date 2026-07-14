import { onBeforeUnmount, onMounted, type Ref } from "vue";

import { isIdleBeyond } from "~/utils/operatorLock";

/**
 * Auto-lock por ociosidade — específico do PDV (kiosk de balcão compartilhado): se
 * ninguém toca a tela por `autoLockSeconds`, o operador ativo é derrubado e a tela
 * de identificação sobe. Os demais apps de operador (KDS/Gestor/Fournil) são estações
 * de um operador só e não auto-travam, por isso isto vive no PDV e não no kit.
 *
 * Fica separado do lock compartilhado (`useOperatorLock`): a identificação em si
 * (PIN/crachá) é a mesma dos outros apps; só o timer de kiosk é do PDV.
 */
export function usePosAutoLock(opts: {
  locked: Ref<boolean>;
  lock: () => void | Promise<void>;
  autoLockSeconds: () => number;
}) {
  let lastActivity = Date.now();
  let cleanup: (() => void) | null = null;

  function markActivity() {
    lastActivity = Date.now();
  }

  onMounted(() => {
    const events: Array<keyof WindowEventMap> = ["pointerdown", "keydown"];
    events.forEach((e) => window.addEventListener(e, markActivity, { passive: true }));
    const id = window.setInterval(() => {
      if (!opts.locked.value && isIdleBeyond(lastActivity, Date.now(), opts.autoLockSeconds() ?? 60)) {
        lastActivity = Date.now(); // evita reentrância enquanto o lock propaga
        opts.lock();
      }
    }, 5000);
    cleanup = () => {
      events.forEach((e) => window.removeEventListener(e, markActivity));
      window.clearInterval(id);
    };
  });

  onBeforeUnmount(() => cleanup?.());
}
