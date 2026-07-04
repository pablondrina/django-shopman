<template>
  <Primitive
    data-slot="empty-icon"
    :data-variant="props.variant"
    :class="emptyMediaStyles({ class: normalizeClass(props.class) || undefined, variant })"
    v-bind="forwarded"
  >
    <slot />
  </Primitive>
</template>

<script lang="ts">
  import { Primitive } from "reka-ui";
  import type { PrimitiveProps } from "reka-ui";
  import type { VariantProps } from "tailwind-variants";
  import { normalizeClass } from "vue";
  import type { HTMLAttributes } from "vue";

  export const emptyMediaStyles = tv({
    base: "mb-2 flex shrink-0 items-center justify-center [&_svg]:pointer-events-none [&_svg]:shrink-0",
    variants: {
      variant: {
        default: "bg-transparent",
        icon: "bg-cta/12 text-cta flex size-12 shrink-0 items-center justify-center rounded-full [&_svg:not([class*='size-'])]:size-6",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  });

  export type EmptyMediaProps = PrimitiveProps & {
    /** Additional classes to apply to the empty media container. */
    class?: HTMLAttributes["class"];
    /**
     * The variant of the empty media component.
     *
     * @default "default"
     */
    variant?: VariantProps<typeof emptyMediaStyles>["variant"];
  };
</script>

<script lang="ts" setup>
  const props = defineProps<EmptyMediaProps>();
  const forwarded = reactiveOmit(props, ["class"]);
</script>
