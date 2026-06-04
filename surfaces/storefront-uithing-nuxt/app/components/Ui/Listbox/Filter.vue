<template>
  <ListboxFilter
    data-slot="listbox-filter"
    v-bind="forwarded"
    :class="props.asChild ? undefined : styles({ class: normalizeClass(props.class) || undefined })"
  >
    <slot />
  </ListboxFilter>
</template>

<script setup lang="ts">
  import { reactiveOmit } from "@vueuse/core";
  import { ListboxFilter, useForwardPropsEmits } from "reka-ui";
  import type { ListboxFilterEmits, ListboxFilterProps } from "reka-ui";
  import { normalizeClass } from "vue";
  import type { HTMLAttributes } from "vue";

  const props = defineProps<ListboxFilterProps & { class?: HTMLAttributes["class"] }>();
  const emits = defineEmits<ListboxFilterEmits>();
  const forwarded = useForwardPropsEmits(reactiveOmit(props, "class"), emits);

  const styles = tv({
    base: "w-full bg-transparent outline-none",
  });
</script>
