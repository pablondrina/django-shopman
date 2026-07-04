<template>
  <ListboxGroup
    data-slot="listbox-group"
    v-bind="forwarded"
    :class="styles({ class: normalizeClass(props.class) || undefined })"
  >
    <slot />
  </ListboxGroup>
</template>

<script setup lang="ts">
  import { reactiveOmit } from "@vueuse/core";
  import { ListboxGroup } from "reka-ui";
  import type { ListboxGroupProps } from "reka-ui";
  import { normalizeClass } from "vue";
  import type { HTMLAttributes } from "vue";

  const props = defineProps<ListboxGroupProps & { class?: HTMLAttributes["class"] }>();
  const forwarded = reactiveOmit(props, "class");

  const styles = tv({
    base: "space-y-1",
  });
</script>
