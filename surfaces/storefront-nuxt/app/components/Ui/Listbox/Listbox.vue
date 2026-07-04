<template>
  <ListboxRoot
    data-slot="listbox"
    v-bind="forwarded"
    :class="styles({ class: normalizeClass(props.class) || undefined })"
  >
    <slot />
  </ListboxRoot>
</template>

<script setup lang="ts">
  import { reactiveOmit } from "@vueuse/core";
  import { ListboxRoot, useForwardPropsEmits } from "reka-ui";
  import type { ListboxRootEmits, ListboxRootProps } from "reka-ui";
  import { normalizeClass } from "vue";
  import type { HTMLAttributes } from "vue";

  const props = defineProps<ListboxRootProps & { class?: HTMLAttributes["class"] }>();
  const emits = defineEmits<ListboxRootEmits>();
  const forwarded = useForwardPropsEmits(reactiveOmit(props, "class"), emits);

  const styles = tv({
    base: "rounded-lg border bg-background p-1 shadow-xs",
  });
</script>
