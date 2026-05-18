<script setup lang="ts">
import type { ProductMutationMeta, ProductResponse } from '~/types/shopman'

const open = defineModel<boolean>('open', { default: false })
const props = defineProps<{
  sku: string | null
}>()

const apiPath = useShopmanApiPath()
const { setFromServer, qtyForSku } = useCartState()

const { data, pending, error, execute } = await useFetch<ProductResponse>(
  () => props.sku ? apiPath(`/api/v1/storefront/products/${encodeURIComponent(props.sku)}/`) : apiPath('/api/v1/storefront/products/__missing__/'),
  {
    immediate: false,
    credentials: 'include'
  }
)

watch(() => [open.value, props.sku] as const, ([isOpen, sku]) => {
  if (isOpen && sku) void execute()
})

watchEffect(() => setFromServer(data.value?.cart))

const product = computed(() => data.value?.product || null)
const meta = computed<ProductMutationMeta | null>(() => product.value
  ? {
      sku: product.value.sku,
      name: product.value.name,
      price_q: product.value.base_price_q,
      price_display: product.value.price_display,
      image_url: product.value.image_url
    }
  : null)
const currentQty = computed(() => product.value ? qtyForSku(product.value.sku) || product.value.qty_in_cart || 0 : 0)
const detailDescription = computed(() => {
  if (!product.value?.long_description) return ''
  return product.value.long_description === product.value.short_description ? '' : product.value.long_description
})
</script>

<template>
  <UiSheet v-model:open="open">
    <UiSheetContent side="right" fullscreen class="overflow-y-auto sm:max-w-2xl">
      <template #header>
        <UiSheetHeader>
          <UiSheetTitle :title="product?.name || 'Produto'" />
          <UiSheetDescription :description="product?.availability_label || 'Detalhes do item'" />
        </UiSheetHeader>
      </template>

      <div v-if="pending" class="space-y-4 p-4">
        <UiSkeleton class="h-64 w-full rounded-lg" />
        <UiSkeleton class="h-8 w-2/3" />
        <UiSkeleton class="h-24 w-full" />
      </div>

      <UiAlert v-else-if="error" variant="destructive" class="m-4">
        <UiAlertTitle>Produto indisponivel</UiAlertTitle>
        <UiAlertDescription>Nao foi possivel carregar os detalhes agora.</UiAlertDescription>
      </UiAlert>

      <article v-else-if="product && meta" class="space-y-5 p-4">
        <div class="overflow-hidden rounded-lg border bg-muted">
          <img
            v-if="product.image_url"
            :src="product.image_url"
            :alt="product.name"
            class="aspect-[4/3] w-full object-cover"
          >
          <div v-else class="flex aspect-[4/3] items-center justify-center text-muted-foreground">
            <Icon name="lucide:image" class="size-10" />
          </div>
        </div>

        <div class="space-y-2">
          <div class="flex flex-wrap gap-2">
            <UiBadge :variant="availabilityVariant(product.availability)">{{ product.availability_label }}</UiBadge>
            <UiBadge v-if="product.promotion_label" variant="warning">{{ product.promotion_label }}</UiBadge>
            <UiBadge v-if="product.is_bundle" variant="info">Combo</UiBadge>
          </div>
          <h2 class="text-2xl font-semibold leading-tight">{{ product.name }}</h2>
          <p v-if="product.short_description" class="text-sm leading-6 text-muted-foreground">{{ product.short_description }}</p>
          <p v-if="detailDescription" class="text-sm leading-6 text-muted-foreground">{{ detailDescription }}</p>
          <div class="flex flex-col items-start gap-4 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <p v-if="product.original_price_display" class="text-sm text-muted-foreground line-through">
                {{ product.original_price_display }}
              </p>
              <p class="text-xl font-semibold">{{ product.price_display }}</p>
            </div>
            <QuantityControl
              :meta="meta"
              :qty="currentQty"
              :disabled="!product.can_add_to_cart"
              :max-qty="product.available_qty ?? product.max_qty"
            />
          </div>
        </div>

        <UiAccordion type="multiple" class="rounded-lg border">
          <UiAccordionItem v-if="product.components.length" value="components">
            <UiAccordionTrigger>Itens do combo</UiAccordionTrigger>
            <UiAccordionContent>
              <ul class="space-y-2 text-sm text-muted-foreground">
                <li v-for="component in product.components" :key="component.sku" class="flex justify-between gap-3">
                  <span>{{ component.name }}</span>
                  <span>{{ component.qty_display }}</span>
                </li>
              </ul>
            </UiAccordionContent>
          </UiAccordionItem>

          <UiAccordionItem v-if="product.allergen?.has_any || product.ingredients_text || product.trace_notice" value="ingredients">
            <UiAccordionTrigger>Ingredientes e seguranca</UiAccordionTrigger>
            <UiAccordionContent>
              <div class="space-y-3 text-sm leading-6 text-muted-foreground">
                <p v-if="product.ingredients_text">{{ product.ingredients_text }}</p>
                <p v-if="product.allergen?.allergens.length">Alergenos: {{ product.allergen.allergens.join(', ') }}</p>
                <p v-if="product.allergen?.dietary_info.length">Dieta: {{ product.allergen.dietary_info.join(', ') }}</p>
                <p v-if="product.trace_notice">{{ product.trace_notice }}</p>
              </div>
            </UiAccordionContent>
          </UiAccordionItem>

          <UiAccordionItem v-if="product.nutrition?.has_any" value="nutrition">
            <UiAccordionTrigger>Informacao nutricional</UiAccordionTrigger>
            <UiAccordionContent>
              <div class="space-y-2 text-sm">
                <p v-if="product.nutrition?.serving_size_display" class="text-muted-foreground">
                  Porcao: {{ product.nutrition.serving_size_display }}
                </p>
                <div v-for="row in product.nutrition?.rows || []" :key="row.field" class="flex justify-between gap-3 border-t py-2">
                  <span>{{ row.label }}</span>
                  <span class="font-medium">{{ row.value_display }}</span>
                </div>
              </div>
            </UiAccordionContent>
          </UiAccordionItem>

          <UiAccordionItem v-if="product.conservation?.has_any || product.unit_weight_label || product.approx_dimensions_label" value="care">
            <UiAccordionTrigger>Conservacao</UiAccordionTrigger>
            <UiAccordionContent>
              <div class="space-y-2 text-sm leading-6 text-muted-foreground">
                <p v-if="product.conservation?.shelf_life_label">{{ product.conservation.shelf_life_label }}</p>
                <p v-if="product.conservation?.storage_tip">{{ product.conservation.storage_tip }}</p>
                <p v-if="product.unit_weight_label">Peso: {{ product.unit_weight_label }}</p>
                <p v-if="product.approx_dimensions_label">Dimensoes: {{ product.approx_dimensions_label }}</p>
              </div>
            </UiAccordionContent>
          </UiAccordionItem>
        </UiAccordion>
      </article>
    </UiSheetContent>
  </UiSheet>
</template>
