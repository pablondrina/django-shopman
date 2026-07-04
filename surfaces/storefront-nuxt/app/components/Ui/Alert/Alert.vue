<template>
  <div
    v-if="shown"
    data-slot="alert"
    :class="
      alertStyles().base({ variant, filled, class: normalizeClass(props.class) || undefined })
    "
  >
    <slot :props="props" name="icon">
      <Icon
        v-if="icon"
        data-slot="alert-icon"
        :name="icon"
        :class="
          alertStyles().icon({
            variant,
            filled,
            class: normalizeClass(props.iconClass) || undefined,
            hasTitle,
          })
        "
      />
    </slot>
    <div data-slot="alert-content" :class="alertStyles().content({ variant, filled })">
      <slot :props="props">
        <slot name="title">
          <UiAlertTitle v-if="title" :title="title" />
        </slot>
        <slot name="description">
          <UiAlertDescription v-if="description" :description="description" />
        </slot>
      </slot>
    </div>
  </div>
</template>

<script lang="ts">
  import { normalizeClass } from "vue";
  import type { HTMLAttributes } from "vue";

  export type AlertProps = {
    /** Custom class to add to the `Alert` parent. */
    class?: HTMLAttributes["class"];
    /** Classes to add to the icon. */
    iconClass?: HTMLAttributes["class"];
    /** Whether the alert should have a filled/colored background. */
    filled?: boolean;
    /**
     * Whether or not the `Alert` is shown.
     *
     * @default true
     */
    modelValue?: boolean;
    /** The variant of the `Alert` */
    variant?: VariantProps<typeof alertStyles>["variant"];
    /** The title that is passed to the `AlertTitle` component. */
    title?: string;
    /** The description that is passed to the `AlertDescription` component. */
    description?: string;
    /** The icon that should be displayed. */
    icon?: string;
  };

  export const alertStyles = tv({
    slots: {
      base: "relative flex w-full gap-3 rounded-lg border p-4",
      icon: "size-4 shrink-0",
      content: "grow",
    },
    variants: {
      variant: {
        default: {
          base: "bg-background text-foreground shadow-xs",
          icon: "text-foreground",
        },
        destructive: {
          base: "border-destructive/50 text-destructive dark:border-destructive",
          icon: "text-destructive",
        },
        info: {
          base: "border-info/40 bg-info/10 text-foreground",
          icon: "text-info",
        },
        success: {
          base: "border-success/40 bg-success/10 text-foreground",
          icon: "text-success",
        },
        warning: {
          base: "border-warning/45 bg-warning/12 text-foreground",
          icon: "text-warning",
        },
      },
      filled: {
        true: {},
      },
      hasTitle: {
        true: {},
        false: { icon: "mt-0.5" },
      },
    },
    defaultVariants: {
      variant: "default",
      filled: false,
    },
    compoundVariants: [
      {
        filled: true,
        variant: "default",
        class: { base: "bg-muted/50 text-foreground", icon: "text-foreground" },
      },
      {
        filled: true,
        variant: "destructive",
        class: {
          base: "bg-destructive text-destructive-foreground shadow-xs",
          icon: "text-destructive-foreground",
        },
      },
      {
        filled: true,
        variant: "info",
        class: { base: "bg-info text-info-foreground shadow-xs", icon: "text-info-foreground" },
      },
      {
        filled: true,
        variant: "success",
        class: { base: "bg-success text-success-foreground shadow-xs", icon: "text-success-foreground" },
      },
      {
        filled: true,
        variant: "warning",
        class: { base: "bg-warning text-warning-foreground shadow-xs", icon: "text-warning-foreground" },
      },
    ],
  });
</script>

<script lang="ts" setup>
  const props = withDefaults(defineProps<AlertProps>(), {
    modelValue: true,
    variant: "default",
  });

  const slots = useSlots();
  const hasTitle = computed(() => !!props.title || !!slots.title);

  const shown = defineModel<boolean>({ default: true });
</script>
