<template>
  <HoverCardPortal data-slot="hover-card-portal" v-bind="props">
    <slot />
  </HoverCardPortal>
</template>

<script lang="ts" setup>
  import { HoverCardPortal } from "reka-ui";
  import type { HoverCardPortalProps } from "reka-ui";

  const props = defineProps<HoverCardPortalProps>();
</script>
