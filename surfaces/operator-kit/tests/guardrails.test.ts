import { readdirSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// Guardrails de CONSISTÊNCIA do design system canônico do backstage (Lente 7).
// Fonte: docs/engineering/backstage-design-system.md. Estes testes travam a DRIFT
// entre as 5 superfícies de operador — os tokens canônicos vivem num tema central
// (operator-theme.css) e cada app o importa; o guardrail garante fonte única +
// importação. Storefront fica FORA (sistema branded próprio).

const surfacesDir = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const OPERATOR_APPS = ["pos-nuxt", "kds-nuxt", "orders-nuxt", "production-nuxt", "hub-nuxt"] as const;

// Tokens canônicos que vivem no tema central e chegam aos 5 apps pela importação.
// Cada app pode ter tokens ADICIONAIS (print no POS, dark no KDS) — o guardrail checa
// a presença dos canônicos na fonte única + a importação, não igualdade byte-a-byte.
const CANONICAL_TOKENS = ["--radius", "--primary", "--destructive", "--background", "--foreground"] as const;

function cssFor(app: string): string {
  return readFileSync(resolve(surfacesDir, app, "app/assets/css/tailwind.css"), "utf8");
}

/** Valor do 1º `--token: <value>;` no bloco :root (light) do css. */
function tokenValue(css: string, token: string): string | null {
  const match = css.match(new RegExp(`${token}\\s*:\\s*([^;]+);`));
  return match ? match[1].trim() : null;
}

describe("design-system: tema operador centralizado (operator-theme.css) herdado por todos", () => {
  // O tema quente do operador vive num ÚNICO arquivo no kit (operator-theme.css),
  // importado por cada app via @import. A paridade de tokens deixa de ser "mesmo
  // valor copiado em 5 tailwind.css" e passa a ser "fonte única + todos importam" —
  // drift torna-se impossível por construção.
  const operatorTheme = readFileSync(
    resolve(surfacesDir, "operator-kit", "app/assets/css/operator-theme.css"),
    "utf8",
  );

  it("os tokens canônicos vivem no operator-theme.css central (fonte única)", () => {
    for (const token of CANONICAL_TOKENS) {
      expect(
        tokenValue(operatorTheme, token),
        `${token} ausente no operator-theme.css central`,
      ).not.toBeNull();
    }
  });

  for (const app of OPERATOR_APPS) {
    it(`${app} importa o operator-theme.css do kit (herda os tokens, zero drift)`, () => {
      expect(cssFor(app), `${app} não importa o tema central`).toMatch(/operator-theme\.css/);
    });
  }
});

// --- Escala tipográfica (DS §3): só os 6 papéis; sem `text-2xl` nem `text-[..]`
// avulso (mesma dívida corrigida no storefront no WP-S0). Aplica-se às superfícies de
// TELA — não à impressão térmica (recibo 80mm tem px fixos, outro meio). A enforcement
// CRESCE por app (cada WP endurece o seu); a allowlist só ENCOLHE.
// As 5 superfícies de operador estão endurecidas. O KDS é distance-first: sua escala de
// densidade mapeia limpo aos papéis do canon (compact=title text-xl · cozy=figure text-3xl
// · roomy=display text-4xl) — nenhum text-2xl/text-[..] avulso, então nada de allowlist.
const TYPOGRAPHY_ENFORCED = ["pos-nuxt", "hub-nuxt", "orders-nuxt", "production-nuxt", "kds-nuxt"] as const;

// Arquivos isentos com justificativa (medium ≠ tela). Chave = caminho relativo ao app.
const TYPOGRAPHY_ALLOWLIST: Record<string, string> = {
  "pos-nuxt/app/components/PosReceipt.vue": "recibo térmico 80mm — px fixos p/ a impressora, não papéis de tela",
  "production-nuxt/app/components/WeighingLabels.vue": "etiquetas de pesagem — papel físico, tamanhos fixos p/ a etiquetadora, não papéis de tela",
};

function walkVueFiles(dir: string, appDir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    // Componentes Ui/** são a família vendada (UI Thing) — fora do canon de tela.
    if (entry.isDirectory()) {
      if (entry.name === "Ui" || entry.name === "node_modules") continue;
      walkVueFiles(full, appDir, out);
    } else if (entry.name.endsWith(".vue")) {
      out.push(full);
    }
  }
  return out;
}

// text-2xl e qualquer arbitrário text-[..] (px/rem) — os dois anti-padrões nomeados no DS.
const STRAY_TEXT = /\btext-2xl\b|\btext-\[[^\]]+\]/g;

describe("design-system: escala tipográfica (só os 6 papéis)", () => {
  for (const app of TYPOGRAPHY_ENFORCED) {
    const appRoot = resolve(surfacesDir, app, "app");
    const files = walkVueFiles(appRoot, appRoot);

    it(`${app}: nenhum text-2xl/text-[..] avulso fora da allowlist`, () => {
      const offenders: string[] = [];
      for (const file of files) {
        const rel = `${app}/app/${file.slice(appRoot.length + 1)}`;
        if (TYPOGRAPHY_ALLOWLIST[rel]) continue;
        const hits = readFileSync(file, "utf8").match(STRAY_TEXT);
        if (hits) offenders.push(`${rel}: ${[...new Set(hits)].join(", ")}`);
      }
      expect(offenders, `tamanhos de texto fora dos papéis:\n${offenders.join("\n")}`).toEqual([]);
    });

    it(`${app}: cada arquivo da allowlist ainda existe (a lista só encolhe)`, () => {
      for (const rel of Object.keys(TYPOGRAPHY_ALLOWLIST)) {
        if (!rel.startsWith(`${app}/`)) continue;
        expect(files.some((f) => `${app}/app/${f.slice(appRoot.length + 1)}` === rel), `allowlist stale: ${rel}`).toBe(true);
      }
    });
  }
});
