<template>
  <ListboxItem
    data-slot="listbox-item"
    v-bind="forwarded"
    :class="styles({ class: normalizeClass(props.class) || undefined })"
  >
    <slot />
  </ListboxItem>
</template>

<script setup lang="ts">
  import { reactiveOmit } from "@vueuse/core";
  import { ListboxItem, useForwardPropsEmits } from "reka-ui";
  import type { ListboxItemEmits, ListboxItemProps } from "reka-ui";
  import { normalizeClass } from "vue";
  import type { HTMLAttributes } from "vue";

  const props = defineProps<ListboxItemProps & { class?: HTMLAttributes["class"] }>();
  const emits = defineEmits<ListboxItemEmits>();
  const forwarded = useForwardPropsEmits(reactiveOmit(props, "class"), emits);

  const styles = tv({
    base: "relative flex w-full cursor-pointer items-center gap-2 rounded-md px-2 py-2 text-sm transition-colors outline-none select-none data-disabled:pointer-events-none data-disabled:opacity-50 data-highlighted:bg-accent data-highlighted:text-accent-foreground data-[state=checked]:bg-accent data-[state=checked]:text-accent-foreground [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  });
</script>
