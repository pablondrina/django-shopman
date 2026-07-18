import { mount } from "@vue/test-utils";
import { computed, ref, watch } from "vue";
import { beforeAll, describe, expect, it } from "vitest";
import BroadcastPostCard from "~/components/BroadcastPostCard.vue";
import type { BroadcastPost } from "~/types/broadcast";

// Sem runtime Nuxt: os auto-imports viram globais e o Icon vira stub.
beforeAll(() => {
  Object.assign(globalThis, { computed, ref, watch });
});

const PLATFORMS = [
  { value: "instagram", label: "Instagram" },
  { value: "google_business", label: "Google Meu Negócio" },
  { value: "whatsapp", label: "WhatsApp" },
];

function makePost(over: Partial<BroadcastPost> = {}): BroadcastPost {
  return {
    pk: 7,
    status: "pending_review",
    status_label: "aguardando aprovação",
    body: "Croissant saiu do forno",
    image_url: "",
    hashtags: ["padaria"],
    link: "/p/croissant",
    platforms: ["instagram"],
    audience: { favorites_count: 12, alerts_count: 3, total: 15 },
    audience_total: 15,
    platform_results: [],
    trigger: "production_finished",
    trigger_label: "fornada concluída",
    rule_name: "Fornada de pães",
    template_name: "Fornada",
    sku: "CRO-001",
    created_at: "2026-07-18T07:00:00-03:00",
    expires_at: "",
    expires_in_minutes: 20,
    published_at: "",
    approved_by: "",
    ...over,
  };
}

function mountCard(post: BroadcastPost) {
  return mount(BroadcastPostCard, {
    props: { post, platformOptions: PLATFORMS },
    global: { stubs: { Icon: true } },
  });
}

describe("BroadcastPostCard", () => {
  it("shows the generated text, the audience and the deadline", () => {
    const text = mountCard(makePost()).text();
    expect(text).toContain("Fornada de pães");
    expect(text).toContain("12 favoritos, 3 alertas = 15 clientes");
    expect(text).toContain("expira em 20 min");
  });

  it("pre-selects exactly the platforms the rule chose", () => {
    const wrapper = mountCard(makePost({ platforms: ["instagram", "whatsapp"] }));
    const checked = wrapper
      .findAll("input[type=checkbox]")
      .filter((input) => (input.element as HTMLInputElement).checked);
    expect(checked).toHaveLength(2);
  });

  it("sends the edited text and platforms together with the approval", async () => {
    // Um request só: salvar e publicar em duas chamadas abriria a janela de
    // publicar a versão anterior.
    const wrapper = mountCard(makePost());
    await wrapper.find("textarea").setValue("Texto revisado");
    await wrapper.find("input[type=text]").setValue("#paes #fornada");
    await wrapper.findAll("button")[0]!.trigger("click");

    expect(wrapper.emitted("approve")).toBeTruthy();
    const [pk, edits] = wrapper.emitted("approve")![0] as [number, Record<string, unknown>];
    expect(pk).toBe(7);
    expect(edits.body).toBe("Texto revisado");
    expect(edits.hashtags).toEqual(["paes", "fornada"]);
    expect(edits.platforms).toEqual(["instagram"]);
  });

  it("refuses to publish an empty post", async () => {
    const wrapper = mountCard(makePost());
    await wrapper.find("textarea").setValue("   ");
    const publish = wrapper.findAll("button")[0]!;

    expect((publish.element as HTMLButtonElement).disabled).toBe(true);
    await publish.trigger("click");
    expect(wrapper.emitted("approve")).toBeFalsy();
  });

  it("refuses to publish with no platform selected", async () => {
    const wrapper = mountCard(makePost({ platforms: [] }));
    expect((wrapper.findAll("button")[0]!.element as HTMLButtonElement).disabled).toBe(true);
    expect(wrapper.text()).toContain("Escolha ao menos uma plataforma");
  });

  it("only asks for a date after the gestor chooses to schedule", async () => {
    const wrapper = mountCard(makePost());
    expect(wrapper.find("input[type=datetime-local]").exists()).toBe(false);

    await wrapper.findAll("button")[1]!.trigger("click");
    expect(wrapper.find("input[type=datetime-local]").exists()).toBe(true);
  });

  it("carries publish_at when scheduling", async () => {
    const wrapper = mountCard(makePost());
    await wrapper.findAll("button")[1]!.trigger("click");
    await wrapper.find("input[type=datetime-local]").setValue("2026-07-19T07:00");
    await wrapper.find("input[type=datetime-local]").trigger("change");

    const confirm = wrapper.findAll("button").at(-1)!;
    await confirm.trigger("click");

    const [, edits] = wrapper.emitted("approve")![0] as [number, Record<string, unknown>];
    expect(edits.publish_at).toBe("2026-07-19T07:00");
  });

  it("asks the parent to confirm the discard instead of discarding itself", async () => {
    const wrapper = mountCard(makePost());
    const discard = wrapper.findAll("button").find((b) => b.text().includes("Descartar"))!;
    await discard.trigger("click");
    expect(wrapper.emitted("discard")![0]).toEqual([7]);
  });

  it("keeps the in-progress edit when the same post is refetched", async () => {
    // Poll/SSE não pode apagar o que o gestor está escrevendo.
    const wrapper = mountCard(makePost());
    await wrapper.find("textarea").setValue("rascunho do gestor");

    await wrapper.setProps({ post: makePost({ body: "texto do servidor" }) });

    expect((wrapper.find("textarea").element as HTMLTextAreaElement).value).toBe(
      "rascunho do gestor",
    );
  });

  it("resets the draft when a different post takes its place", async () => {
    const wrapper = mountCard(makePost());
    await wrapper.find("textarea").setValue("rascunho do post 7");

    await wrapper.setProps({ post: makePost({ pk: 9, body: "outro post" }) });

    expect((wrapper.find("textarea").element as HTMLTextAreaElement).value).toBe("outro post");
  });

  it("offers a placeholder when the product has no photo", () => {
    expect(mountCard(makePost({ image_url: "" })).find("img").exists()).toBe(false);
  });
});
