<template>
  <ListboxContent
    data-slot="listbox-content"
    v-bind="forwarded"
    :class="styles({ class: normalizeClass(props.class) || undefined })"
  >
    <slot />
  </ListboxContent>
</template>

<script setup lang="ts">
  import { reactiveOmit } from "@vueuse/core";
  import { ListboxContent } from "reka-ui";
  import type { ListboxContentProps } from "reka-ui";
  import { normalizeClass } from "vue";
  import type { HTMLAttributes } from "vue";

  const props = defineProps<ListboxContentProps & { class?: HTMLAttributes["class"] }>();
  const forwarded = reactiveOmit(props, "class");

  const styles = tv({
    base: "space-y-1 outline-none",
  });
</script>
