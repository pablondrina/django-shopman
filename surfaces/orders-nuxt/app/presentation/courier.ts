// Courier ride presentation — pure functions over the raw Machine status letter
// (D/G/P/A/S/E/F/N/C/U). The label text comes from the server projection
// (single source of truth); here we derive the compact step timeline and tones.

export type CourierTone = "muted" | "info" | "active" | "success" | "danger";

export interface CourierStep {
  key: "requested" | "accepted" | "picked_up" | "delivered";
  label: string;
  state: "done" | "current" | "pending";
}

/** Ride phases in board order. N/C (failed) short-circuit the timeline. */
const STEP_INDEX: Record<string, number> = {
  D: 0, // distribuindo
  G: 0, // aguardando aceite
  P: 0, // pendente (buscando entregador)
  U: 0, // agrupada — segue buscando/roteirizando
  A: 1, // aceita — entregador a caminho da loja
  S: 1, // em espera — entregador na loja
  E: 2, // em andamento — coletou, saiu para entrega
  F: 3, // finalizada
};

const STEPS: { key: CourierStep["key"]; label: string }[] = [
  { key: "requested", label: "Solicitado" },
  { key: "accepted", label: "Aceito" },
  { key: "picked_up", label: "Coletado" },
  { key: "delivered", label: "Entregue" },
];

export function courierFailed(letter: string): boolean {
  return letter === "N" || letter === "C";
}

/** Compact 4-step timeline for the ride panel. Empty for failed/blank status. */
export function courierSteps(letter: string): CourierStep[] {
  const idx = STEP_INDEX[letter];
  if (idx === undefined) return [];
  return STEPS.map((step, i) => ({
    ...step,
    state: i < idx ? "done" : i === idx ? (letter === "F" ? "done" : "current") : "pending",
  }));
}

/** Visual tone for the ride status badge. */
export function courierTone(letter: string): CourierTone {
  if (courierFailed(letter)) return "danger";
  if (letter === "F") return "success";
  if (letter === "E") return "active";
  if (letter === "A" || letter === "S") return "info";
  if (letter === "D" || letter === "G" || letter === "P" || letter === "U") return "muted";
  return "muted";
}

/** Badge classes per tone (Tailwind design tokens already in the app). */
export function courierToneBadge(tone: CourierTone): string {
  switch (tone) {
    case "danger":
      return "border-red-500/40 bg-red-500/10 text-red-700 dark:text-red-300";
    case "success":
      return "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300";
    case "active":
      return "border-primary/40 bg-primary/10 text-primary";
    case "info":
      return "border-sky-500/40 bg-sky-500/10 text-sky-700 dark:text-sky-300";
    default:
      return "border-border bg-muted text-muted-foreground";
  }
}
