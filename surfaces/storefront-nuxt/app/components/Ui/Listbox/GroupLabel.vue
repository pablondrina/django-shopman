<template>
  <ListboxGroupLabel
    data-slot="listbox-group-label"
    v-bind="forwarded"
    :class="styles({ class: normalizeClass(props.class) || undefined })"
  >
    <slot />
  </ListboxGroupLabel>
</template>

<script setup lang="ts">
  import { reactiveOmit } from "@vueuse/core";
  import { ListboxGroupLabel } from "reka-ui";
  import type { ListboxGroupLabelProps } from "reka-ui";
  import { normalizeClass } from "vue";
  import type { HTMLAttributes } from "vue";

  const props = defineProps<ListboxGroupLabelProps & { class?: HTMLAttributes["class"] }>();
  const forwarded = reactiveOmit(props, "class");

  const styles = tv({
    base: "px-2 py-1.5 text-xs font-medium text-muted-foreground",
  });
</script>
