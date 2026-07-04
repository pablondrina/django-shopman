import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// Guardrails de CONSISTÊNCIA do design system canônico do backstage (Lente 7).
// Fonte: docs/engineering/backstage-design-system.md. Estes testes travam a DRIFT
// entre as 4 superfícies de operador — falham no instante em que alguém edita um
// tailwind.css e não os outros. Storefront fica FORA (sistema branded próprio).

const surfacesDir = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const OPERATOR_APPS = ["pos-nuxt", "kds-nuxt", "orders-nuxt", "production-nuxt"] as const;

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

// TODO(WP-B0 → por-app): estender o scaffold com as demais checagens da Lente 7
// conforme cada app é endurecido, cada uma retirando sua dívida da allowlist:
//   - escala tipográfica (só os 6 papéis; sem text-2xl/text-[..] avulso)
//   - raio/seleção (sem rounded-lg/xl avulso; sem ring colorido em seleção)
//   - alvos de toque ≥ 44px onde a regra se aplica
//   - ícone forte declarado por app
//   - a11y: input de crachá não aria-hidden porém focável (WCAG 4.1.2)
