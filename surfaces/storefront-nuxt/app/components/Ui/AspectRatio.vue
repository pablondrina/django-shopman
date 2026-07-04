<template>
  <AspectRatio v-slot="slotProps" data-slot="aspect-ratio" v-bind="props">
    <slot v-bind="slotProps" />
  </AspectRatio>
</template>

<script lang="ts" setup>
  import { AspectRatio } from "reka-ui";
  import type { AspectRatioProps } from "reka-ui";

  const props = defineProps<AspectRatioProps>();
</script>
