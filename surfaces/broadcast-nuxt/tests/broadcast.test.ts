import { describe, expect, it } from "vitest";
import {
  audienceRulesSummary,
  audienceSummary,
  displayHashtag,
  expiryLabel,
  expiryTone,
  isStillReviewable,
  parseHashtags,
  platformsSummary,
  postOutcome,
  resultLabel,
  resultTone,
  shortDateTime,
  vipSummary,
} from "~/presentation/broadcast";
import type { BroadcastPost, PlatformResult } from "~/types/broadcast";

function result(platform: string, status: string): PlatformResult {
  return { platform, label: platform, status, detail: "", url: "" };
}

describe("audienceSummary", () => {
  it("lists each source and closes with the deduplicated total", () => {
    expect(audienceSummary({ favorites_count: 12, recompra_count: 28, alerts_count: 3, total: 43 }))
      .toBe("12 favoritos, 28 recompra, 3 alertas = 43 clientes");
  });

  it("uses the backend total instead of summing the parts", () => {
    // Quem favoritou E recompra é uma pessoa só: somar (12+28) mentiria pra cima.
    expect(audienceSummary({ favorites_count: 12, recompra_count: 28, total: 30 }))
      .toBe("12 favoritos, 28 recompra = 30 clientes");
  });

  it("omits sources that resolved to nobody", () => {
    expect(audienceSummary({ favorites_count: 5, alerts_count: 0, total: 5 }))
      .toBe("5 favoritos = 5 clientes");
  });

  it("says nobody rather than showing a zero", () => {
    expect(audienceSummary({ total: 0 })).toBe("Ninguém para avisar por enquanto");
    expect(audienceSummary(undefined)).toBe("Ninguém para avisar por enquanto");
  });

  it("agrees in the singular", () => {
    expect(audienceSummary({ alerts_count: 1, total: 1 })).toBe("1 alertas = 1 cliente");
  });

  it("falls back to the bare total when no source is broken out", () => {
    expect(audienceSummary({ total: 7 })).toBe("7 clientes");
  });
});

describe("vipSummary", () => {
  it("states the head start", () => {
    expect(vipSummary({ vip_count: 4, vip_delay_minutes: 15 })).toBe("4 VIPs recebem 15 min antes");
  });

  it("stays silent when there is no head start to talk about", () => {
    expect(vipSummary({ vip_count: 4, vip_delay_minutes: 0 })).toBe("");
    expect(vipSummary({ vip_count: 0, vip_delay_minutes: 15 })).toBe("");
    expect(vipSummary(undefined)).toBe("");
  });
});

describe("expiryLabel", () => {
  it("reads in minutes under an hour and in hours above it", () => {
    expect(expiryLabel(12)).toBe("expira em 12 min");
    expect(expiryLabel(59)).toBe("expira em 59 min");
    expect(expiryLabel(90)).toBe("expira em 1 h");
  });

  it("says the deadline passed instead of showing zero", () => {
    expect(expiryLabel(0)).toBe("expirou");
  });

  it("stays silent for posts with no deadline", () => {
    expect(expiryLabel(-1)).toBe("");
  });
});

describe("expiryTone", () => {
  it("escalates as the window closes", () => {
    expect(expiryTone(5)).toBe("urgent");
    expect(expiryTone(25)).toBe("warning");
    expect(expiryTone(120)).toBe("calm");
  });

  it("does not shout when there is no deadline", () => {
    expect(expiryTone(-1)).toBe("none");
  });
});

describe("postOutcome", () => {
  it("only calls it published when every platform published", () => {
    expect(postOutcome([result("instagram", "published"), result("tv", "published")]))
      .toBe("published");
  });

  it("treats a mixed result as partial, not as success", () => {
    expect(postOutcome([result("instagram", "failed"), result("tv", "published")]))
      .toBe("partial");
  });

  it("reports a total failure as failed", () => {
    expect(postOutcome([result("instagram", "failed")])).toBe("failed");
  });

  it("counts a WhatsApp-only wave as published once it was sent", () => {
    expect(postOutcome([result("whatsapp", "sent")])).toBe("published");
  });

  it("counts a still-queued platform as pending", () => {
    expect(postOutcome([result("instagram", "queued"), result("tv", "pending_manual")]))
      .toBe("pending");
  });

  it("treats a post with no targeted platform as pending", () => {
    expect(postOutcome([])).toBe("pending");
  });
});

describe("resultTone", () => {
  it("maps a manual pending to pending, never to failure", () => {
    // Sem credencial, o post fica pending_manual DE PROPÓSITO — não é erro.
    expect(resultTone("pending_manual")).toBe("pending");
    expect(resultTone("published")).toBe("ok");
    expect(resultTone("failed")).toBe("fail");
  });

  it("treats the WhatsApp `sent` as a success, not as an unknown", () => {
    // O handler grava `sent` para a onda de WhatsApp; ler isso como pendente
    // deixaria um post inteiramente entregue parecendo travado.
    expect(resultTone("sent")).toBe("ok");
    expect(resultLabel("sent")).toBe("enviado");
  });

  it("shows an unmapped status verbatim instead of swallowing it", () => {
    expect(resultLabel("mystery")).toBe("mystery");
  });
});

describe("hashtags", () => {
  it("reads with a single # no matter how it was stored", () => {
    expect(displayHashtag("padaria")).toBe("#padaria");
    expect(displayHashtag("##padaria")).toBe("#padaria");
    expect(displayHashtag("  ")).toBe("");
  });

  it("parses whatever the gestor pasted", () => {
    expect(parseHashtags("#padaria #fornada")).toEqual(["padaria", "fornada"]);
    expect(parseHashtags("padaria, fornada")).toEqual(["padaria", "fornada"]);
    expect(parseHashtags("  #padaria \n fornada  ")).toEqual(["padaria", "fornada"]);
    expect(parseHashtags("")).toEqual([]);
  });
});

describe("audienceRulesSummary", () => {
  it("spells out the sources in order", () => {
    expect(audienceRulesSummary({ favorites: true, alerts: true, recompra_days: 90 }))
      .toBe("favoritos, alertas, recompra em 90 dias");
  });

  it("appends the VIP head start", () => {
    expect(audienceRulesSummary({ favorites: true, vip_first_minutes: 15 }))
      .toBe("favoritos, VIP 15 min antes");
  });

  it("is explicit when the rule notifies nobody directly", () => {
    expect(audienceRulesSummary({})).toBe("Sem audiência direta");
    expect(audienceRulesSummary(undefined)).toBe("Sem audiência direta");
  });
});

describe("platformsSummary", () => {
  const labels = { instagram: "Instagram", google_business: "Google Meu Negócio" };

  it("uses the labels and keeps the chosen order", () => {
    expect(platformsSummary(["google_business", "instagram"], labels))
      .toBe("Google Meu Negócio, Instagram");
  });

  it("falls back to the ref when a label is unknown", () => {
    expect(platformsSummary(["mastodon"], labels)).toBe("mastodon");
  });

  it("says none instead of rendering an empty string", () => {
    expect(platformsSummary([], labels)).toBe("Nenhuma plataforma");
  });
});

describe("shortDateTime", () => {
  it("returns empty for a missing or unparseable date, never Invalid Date", () => {
    expect(shortDateTime("")).toBe("");
    expect(shortDateTime("amanhã")).toBe("");
  });

  it("formats a real ISO timestamp", () => {
    expect(shortDateTime("2026-07-18T07:30:00-03:00")).toMatch(/\d{2}\/\d{2}/);
  });
});

describe("isStillReviewable", () => {
  const post = (over: Partial<BroadcastPost>) =>
    ({ status: "pending_review", expires_in_minutes: 30, ...over }) as BroadcastPost;

  it("accepts a pending post inside its window", () => {
    expect(isStillReviewable(post({}))).toBe(true);
  });

  it("accepts a pending post with no deadline", () => {
    expect(isStillReviewable(post({ expires_in_minutes: -1 }))).toBe(true);
  });

  it("refuses one whose deadline already passed", () => {
    // O sweeper roda em ciclos de minutos: a tela não pode oferecer "Publicar"
    // num card que venceu entre um fetch e outro.
    expect(isStillReviewable(post({ expires_in_minutes: 0 }))).toBe(false);
  });

  it("refuses one that was already decided", () => {
    expect(isStillReviewable(post({ status: "published" }))).toBe(false);
  });
});
