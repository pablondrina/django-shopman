// Weighing read-side (per-prep tickets). Backs the "Por preparo" mode of the
// Preparação page and the blind-label print run: each ticket is one prep with
// its ingredients already scaled by the day's planned coefficient, plus the
// day's blind code (the only identity that goes on paper).
import type { Ref } from "vue";
import type { WeighingResponse, WeighingTicketProjection } from "~/types/production";

export function useWeighing(selectedDate: Ref<string>) {
  const { data, pending, error, refresh } = useFetch<WeighingResponse>(
    "/api/v1/backstage/production/weighing/",
    {
      key: "production-weighing",
      server: true,
      query: computed(() => ({ date: selectedDate.value })),
    },
  );

  const tickets = computed<WeighingTicketProjection[]>(() => data.value?.weighing?.tickets ?? []);
  const dateDisplay = computed(() => data.value?.weighing?.selected_date_display ?? "");

  useAdaptivePoll(refresh, () => 60_000);

  return { tickets, dateDisplay, pending, error, refresh };
}
