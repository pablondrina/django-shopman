// Proxy BFF canônico das superfícies de operador (server/utils/djangoProxy.ts).
// Exercita as decisões de transporte de CSRF/cookie — preservar a sessão ao
// atualizar o csrftoken, valores com "=" (assinados/base64) intactos — e trava
// por fonte as decisões de segurança/contrato: origin normalizado para o do
// Django e checagem de X-API-Version fiada dentro do proxy (PR #71). Espelha a
// suíte do storefront (djangoProxy.test.ts), que mantém proxy próprio.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { csrfTokenFromCookieHeader, mergeSetCookieIntoCookieHeader } from "../server/utils/djangoProxy";

const proxySource = readFileSync(fileURLToPath(new URL("../server/utils/djangoProxy.ts", import.meta.url)), "utf8");

describe("Django proxy — transporte de CSRF/cookie do BFF de operador", () => {
  it("preserva o cookie de sessão do Django ao atualizar o estado de CSRF", () => {
    const cookie = "sessionid=session-123; csrftoken=old-token";
    expect(csrfTokenFromCookieHeader(cookie)).toBe("old-token");
    expect(mergeSetCookieIntoCookieHeader(cookie, "csrftoken=new-token; Path=/; SameSite=Lax")).toBe(
      "sessionid=session-123; csrftoken=new-token",
    );
    expect(mergeSetCookieIntoCookieHeader(cookie, "other=value=with-equals; Path=/")).toBe(
      "sessionid=session-123; csrftoken=old-token; other=value=with-equals",
    );
  });

  it('mantém valores de cookie com "=" intactos (assinados/base64)', () => {
    const cookie = "csrftoken=old-token";
    expect(mergeSetCookieIntoCookieHeader(cookie, "sessionid=abc.def=ghi==; Path=/; HttpOnly")).toBe(
      "csrftoken=old-token; sessionid=abc.def=ghi==",
    );
  });

  it("normaliza origin/referer de método inseguro para o origin do Django", () => {
    expect(proxySource).toContain("headers.origin = djangoOrigin");
    expect(proxySource).toContain("headers.referer = `${djangoOrigin}/`");
    expect(proxySource).not.toContain('getRequestHeader(event, "origin")');
    expect(proxySource).not.toContain('getRequestHeader(event, "referer")');
  });

  it("mantém a checagem de X-API-Version fiada dentro do proxy", () => {
    expect(proxySource).toContain('warnOnApiVersionMismatch(response.headers.get("x-api-version")');
  });
});
