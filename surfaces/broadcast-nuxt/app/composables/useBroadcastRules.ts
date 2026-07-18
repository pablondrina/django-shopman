// Regras de broadcast — listagem, liga/desliga e o CRUD leve do formulário.
//
// As "options" (gatilhos, plataformas, modelos, variáveis) vêm do backend em vez
// de hardcoded na tela: gatilho novo no domínio aparece no formulário sem deploy
// de front, e a lista nunca diverge da que o serviço aceita.
import type { BroadcastRule, OptionsResponse, RulesResponse } from "~/types/broadcast";

export function useBroadcastRules() {
  const { data, refresh, pending, error } = useFetch<RulesResponse>(
    "/api/v1/backstage/broadcast/rules/",
    { key: "broadcast-rules", server: true },
  );
  const { data: optionsData } = useFetch<OptionsResponse>(
    "/api/v1/backstage/broadcast/options/",
    { key: "broadcast-options", server: true },
  );

  const rules = computed<BroadcastRule[]>(() => data.value?.rules ?? []);
  const options = computed(() => optionsData.value?.options);
  const templates = computed(() => options.value?.templates ?? []);
  const triggers = computed(() => options.value?.triggers ?? []);
  const platforms = computed(() => options.value?.platforms ?? []);
  const variables = computed(() => options.value?.variables ?? []);

  /** Rótulo por ref de plataforma — o que `platformsSummary` espera. */
  const platformLabels = computed<Record<string, string>>(() =>
    Object.fromEntries(platforms.value.map((choice) => [choice.value, choice.label])),
  );

  async function toggle(rule: BroadcastRule): Promise<void> {
    await patch(rule.pk, { is_active: !rule.is_active });
  }

  async function patch(pk: number, body: Partial<BroadcastRule> & Record<string, unknown>) {
    try {
      await $fetch(`/api/v1/backstage/broadcast/rules/${pk}/`, { method: "PATCH", body });
      useSonner.success("Regra salva.");
      await refresh();
      return true;
    } catch (err) {
      useSonner.error(httpErrorMessage(err, "Não foi possível salvar a regra."));
      return false;
    }
  }

  async function create(body: Record<string, unknown>) {
    try {
      await $fetch("/api/v1/backstage/broadcast/rules/", { method: "POST", body });
      useSonner.success("Regra criada.");
      await refresh();
      return true;
    } catch (err) {
      useSonner.error(httpErrorMessage(err, "Não foi possível criar a regra."));
      return false;
    }
  }

  return {
    rules,
    options,
    templates,
    triggers,
    platforms,
    platformLabels,
    variables,
    loading: pending,
    error,
    refresh,
    toggle,
    patch,
    create,
  };
}
