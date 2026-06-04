<template>
  <HoverCardRoot data-slot="hover-card" v-bind="forwarded">
    <slot />
  </HoverCardRoot>
</template>

<script lang="ts" setup>
  import { HoverCardRoot, useForwardPropsEmits } from "reka-ui";
  import type { HoverCardRootEmits, HoverCardRootProps } from "reka-ui";

  const props = withDefaults(defineProps<HoverCardRootProps>(), {
    openDelay: 200,
    closeDelay: 200,
  });

  const emits = defineEmits<HoverCardRootEmits>();
  const forwarded = useForwardPropsEmits(props, emits);
</script>
