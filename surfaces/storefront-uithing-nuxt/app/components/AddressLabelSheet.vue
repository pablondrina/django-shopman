<script setup lang="ts">
// Etiqueta DEPOIS de salvar (ADDRESS-UX-PLAN): modal discreto perguntando
// "Casa/Trabalho/Outro…" só quando o endereço JÁ está persistido. Componente
// único — usado pelo checkout (pós-pedido) e pela conta. Faz o próprio PATCH
// da etiqueta; fechar por gesto (X/overlay/ESC) vale como "Agora não".
import { ADDRESS_LABEL_OPTIONS, labelPatchPayload, type AddressLabelKey } from '~/presentation/address'

const props = defineProps<{
  open: boolean
  addressId: number | null
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  resolved: []
}>()

const apiPath = useShopmanApiPath()
const csrfHeaders = useShopmanCsrfHeaders()

const labelOptions = ADDRESS_LABEL_OPTIONS
const customOpen = ref(false)
const custom = ref('')
const saving = ref(false)
let resolvedOnce = false

async function choose (key: AddressLabelKey) {
  if (key === 'other' && !customOpen.value) {
    customOpen.value = true
    return
  }
  if (props.addressId) {
    saving.value = true
    try {
      await $fetch(apiPath(`/api/v1/account/addresses/${encodeURIComponent(props.addressId)}/`), {
        method: 'PATCH',
        headers: await csrfHeaders(),
        credentials: 'include',
        body: labelPatchPayload(key, custom.value)
      })
    } catch {
      // Etiqueta é açúcar — não trava o fluxo se o PATCH falhar.
    } finally {
      saving.value = false
    }
  }
  close()
}

function skip () {
  close()
}

function reset () {
  customOpen.value = false
  custom.value = ''
}

function close () {
  resolvedOnce = true
  emit('update:open', false)
  reset()
  emit('resolved')
}

watch(() => props.open, open => {
  if (open) {
    resolvedOnce = false
    return
  }
  // Fechou por gesto (sem escolher/pular) = "Agora não": resolve mesmo assim.
  if (!resolvedOnce) {
    reset()
    emit('resolved')
  }
})
</script>

<template>
  <UiSheet :open="open" @update:open="value => emit('update:open', value)">
    <UiSheetContent
      side="bottom"
      variant="floating"
      class="mx-auto w-[calc(100%-2rem)] max-w-md gap-0 p-0"
      data-address-label-sheet
    >
      <UiSheetHeader class="px-5 pt-5">
        <UiSheetTitle title="Endereço salvo" />
        <UiSheetDescription description="Como você quer chamar este endereço?" />
      </UiSheetHeader>
      <div class="space-y-3 px-5 pb-5 pt-3">
        <div class="flex flex-wrap gap-2">
          <UiButton
            v-for="option in labelOptions"
            :key="option.key"
            variant="outline"
            size="lg"
            :icon="option.icon"
            :loading="saving && option.key !== 'other'"
            @click="choose(option.key)"
          >
            {{ option.label }}
          </UiButton>
        </div>
        <div v-if="customOpen" class="flex items-start gap-2">
          <UiInput v-model="custom" class="min-w-0 flex-1" placeholder="Ex: Casa da mãe" aria-label="Nome da etiqueta" />
          <UiButton size="lg" :loading="saving" :disabled="!custom.trim()" @click="choose('other')">Salvar</UiButton>
        </div>
        <UiButton variant="ghost" size="sm" class="-ml-2 text-muted-foreground hover:text-foreground" @click="skip">
          Agora não
        </UiButton>
      </div>
    </UiSheetContent>
  </UiSheet>
</template>
