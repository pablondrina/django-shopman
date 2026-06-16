<template>
  <nav
    ref="navRef"
    data-slot="breadcrumb"
    aria-label="breadcrumb"
    :class="styles({ class: normalizeClass(props.class) || undefined })"
  >
    <template v-for="(item, i) in displayItems" :key="i">
      <slot :name="item.slot || 'default'">
        <div
          data-slot="breadcrumb-item"
          class="flex shrink-0 items-center gap-3"
        >
          <div class="group flex items-center gap-2">
            <slot name="crumbIcon" :item="item" :index="i">
              <Icon
                v-if="item.icon"
                data-slot="breadcrumb-icon"
                :name="item.icon"
                class="size-3.5 shrink-0"
                :class="[
                  !isLastItem(i)
                    ? 'text-muted-foreground group-hover:text-foreground'
                    : 'text-primary',
                ]"
              />
            </slot>
            <slot :item="item" :is-not-last-item="(idx: number) => !isLastItem(idx)" :index="i" name="link">
              <NuxtLink
                v-if="item.label"
                :to="!item?.disabled ? item.link : ''"
                data-slot="breadcrumb-label"
                :class="[
                  item.link && !item.disabled && 'underline-offset-2 group-hover:underline',
                  !isLastItem(i)
                    ? 'text-muted-foreground group-hover:text-foreground'
                    : 'text-primary font-medium',
                ]"
                class="text-foreground whitespace-nowrap text-sm transition-colors"
                @click="item?.click?.()"
                >{{ item.label }}</NuxtLink
              >
            </slot>
          </div>
        </div>
      </slot>
      <slot name="separator" :item="item" :index="i">
        <Icon
          v-if="!isLastItem(i)"
          data-slot="breadcrumb-separator"
          :name="separator"
          class="text-muted-foreground h-3 w-3 shrink-0"
        />
      </slot>
    </template>
  </nav>
</template>

<script lang="ts">
  import { normalizeClass } from "vue";
</script>

<script setup lang="ts">
  import type { HTMLAttributes } from "vue";

  export interface BreadcrumbItem {
    label?: string;
    icon?: string;
    link?: string;
    disabled?: boolean;
    slot?: string;
    // eslint-disable-next-line @typescript-eslint/no-unsafe-function-type
    click?: Function;
  }

  const props = withDefaults(
    defineProps<{
      /** The items to display in the breadcrumbs. */
      items?: BreadcrumbItem[];
      /** The separator to use between each breadcrumb. */
      separator?: string;
      /** Custom class(es) to add to the parent element. */
      class?: HTMLAttributes["class"];
    }>(),
    {
      separator: "lucide:chevron-right",
      items: () => [],
    }
  );

  // Regra (portada do storefront Django): o breadcrumb NUNCA quebra linha. O último
  // nível aparece sempre na íntegra; os níveis internos colapsam num único "•••" quando
  // não cabem (3 bullets na meia-altura — mais evidentes que o "…" no baseline). O
  // "•••" leva ao nível-pai (último item interno escondido).
  const navRef = ref<HTMLElement | null>(null);
  const collapsed = ref(false);
  let ro: ResizeObserver | null = null;

  const displayItems = computed<BreadcrumbItem[]>(() => {
    const items = props.items ?? [];
    if (!collapsed.value || items.length <= 2) return items;
    const parent = items[items.length - 2];
    return [
      items[0],
      { label: "•••", link: parent?.link, disabled: !parent?.link },
      items[items.length - 1],
    ];
  });

  const isLastItem = (index: number) => index === displayItems.value.length - 1;

  function measure() {
    if (!import.meta.client) return;
    const el = navRef.value;
    if (!el) return;
    // Mede com tudo expandido; só então decide o colapso (evita loop: o observer
    // escuta o CONTÊINER pai, cuja largura não muda quando o conteúdo colapsa).
    collapsed.value = false;
    nextTick(() => {
      const node = navRef.value;
      if (!node) return;
      collapsed.value = node.scrollWidth > node.clientWidth + 1;
    });
  }

  onMounted(() => {
    measure();
    const target = navRef.value?.parentElement;
    if (target && typeof ResizeObserver !== "undefined") {
      ro = new ResizeObserver(() => measure());
      ro.observe(target);
    }
  });

  onBeforeUnmount(() => ro?.disconnect());
  watch(() => props.items, () => measure(), { deep: true });

  const styles = tv({
    base: "flex w-full min-w-0 flex-nowrap items-center gap-1.5 overflow-hidden text-sm sm:gap-2.5",
  });
</script>
