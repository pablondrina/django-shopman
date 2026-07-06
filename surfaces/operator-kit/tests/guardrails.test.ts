import { readdirSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// Guardrails de CONSISTÊNCIA do design system canônico do backstage (Lente 7).
// Fonte: docs/engineering/backstage-design-system.md. Estes testes travam a DRIFT
// entre as 4 superfícies de operador — falham no instante em que alguém edita um
// tailwind.css e não os outros. Storefront fica FORA (sistema branded próprio).

const surfacesDir = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const OPERATOR_APPS = ["pos-nuxt", "kds-nuxt", "orders-nuxt", "production-nuxt", "hub-nuxt"] as const;

// Tokens canônicos que DEVEM ter o mesmo valor nos 4 apps (cor neutra, raio, semânticos).
// Cada app pode ter tokens ADICIONAIS (print no POS, dark no KDS) — o guardrail checa
// paridade só dos canônicos, não igualdade byte-a-byte do arquivo.
const CANONICAL_TOKENS = ["--radius", "--primary", "--destructive", "--background", "--foreground"] as const;

function cssFor(app: string): string {
  return readFileSync(resolve(surfacesDir, app, "app/assets/css/tailwind.css"), "utf8");
}

/** Valor do 1º `--token: <value>;` no bloco :root (light) do css. */
function tokenValue(css: string, token: string): string | null {
  const match = css.match(new RegExp(`${token}\\s*:\\s*([^;]+);`));
  return match ? match[1].trim() : null;
}

describe("design-system: paridade de tokens canônicos entre os 4 apps de operador", () => {
  const reference = cssFor(OPERATOR_APPS[0]);

  for (const token of CANONICAL_TOKENS) {
    it(`'${token}' é idêntico nos 4 apps`, () => {
      const refValue = tokenValue(reference, token);
      expect(refValue, `${token} ausente em ${OPERATOR_APPS[0]}`).not.toBeNull();
      for (const app of OPERATOR_APPS) {
        expect(tokenValue(cssFor(app), token), `${token} diverge em ${app}`).toBe(refValue);
      }
    });
  }

  it("o token neutro do canon (--primary) permanece neutro (sem matiz de marca)", () => {
    // Disciplina Odoo/ERP: primary é cinza OKLch (chroma ~0), a marca vive no storefront.
    const value = tokenValue(reference, "--primary") ?? "";
    const chroma = Number(value.replace(/oklch\(|\)/g, "").trim().split(/\s+/)[1] ?? "1");
    expect(chroma).toBeLessThan(0.02);
  });
});

// --- Escala tipográfica (DS §3): só os 6 papéis; sem `text-2xl` nem `text-[..]`
// avulso (mesma dívida corrigida no storefront no WP-S0). Aplica-se às superfícies de
// TELA — não à impressão térmica (recibo 80mm tem px fixos, outro meio). A enforcement
// CRESCE por app (cada WP endurece o seu); a allowlist só ENCOLHE.
const TYPOGRAPHY_ENFORCED = ["pos-nuxt", "hub-nuxt", "orders-nuxt", "production-nuxt"] as const; // + kds quando endurecido

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
