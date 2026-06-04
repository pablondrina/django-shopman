<template>
  <ListboxItemIndicator data-slot="listbox-item-indicator" v-bind="forwarded">
    <slot>
      <Icon :name="icon" class="size-4" />
    </slot>
  </ListboxItemIndicator>
</template>

<script setup lang="ts">
  import { reactiveOmit } from "@vueuse/core";
  import { ListboxItemIndicator } from "reka-ui";
  import type { ListboxItemIndicatorProps } from "reka-ui";

  const props = withDefaults(
    defineProps<ListboxItemIndicatorProps & { icon?: string }>(),
    { icon: "lucide:check" }
  );
  const forwarded = reactiveOmit(props, "icon");
</script>
