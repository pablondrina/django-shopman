<script setup lang="ts">
import { phoneDisplay } from '~/utils/authPhone'
import type { WhatsappStartStatus } from '~/composables/useWhatsappVerify'

// Painel APRESENTACIONAL do login por WhatsApp (fluxo access-link). O start leve vive
// no pai (entrar.vue): abrimos o WhatsApp com a mensagem pronta; o cliente envia e toca
// no link que o ManyChat devolve para entrar. Sem polling/espera — a aba só instrui.
const props = withDefaults(defineProps<{
  deepLink?: string
  code?: string
  waNumber?: string
  status?: WhatsappStartStatus
}>(), { deepLink: '', code: '', waNumber: '', status: 'idle' })

const emit = defineEmits<{
  sms: []
  back: []
  regenerate: []
}>()

const codeCopied = ref(false)
// 554333231997 → "(43) 3323-1997"; chat "cru" (sem mensagem) para o envio manual.
const waNumberDisplay = computed(() => props.waNumber ? phoneDisplay(`+${props.waNumber}`) : '')
const chatLink = computed(() => props.waNumber ? `https://wa.me/${props.waNumber}` : '')

async function copyCode () {
  if (!import.meta.client || !props.code) return
  try {
    await navigator.clipboard.writeText(props.code)
    codeCopied.value = true
    useSonner.success('Código copiado. Envie no nosso WhatsApp.')
    setTimeout(() => { codeCopied.value = false }, 2500)
  } catch {
    // Clipboard indisponível: o código continua visível para digitar.
  }
}
</script>

<template>
  <section class="shop-stack-block" data-login-whatsapp aria-live="polite">
    <div class="rounded-lg border bg-bottomnav p-4 shop-stack-block">
      <template v-if="status === 'error'">
        <UiAlert variant="destructive">
          <UiAlertTitle>Não deu para iniciar pelo WhatsApp</UiAlertTitle>
          <UiAlertDescription>Tente de novo ou receba um código por SMS.</UiAlertDescription>
        </UiAlert>
        <UiButton type="button" size="lg" icon="lucide:rotate-cw" class="w-full justify-center" @click="emit('regenerate')">
          Tentar de novo
        </UiButton>
      </template>

      <template v-else>
        <!-- A AÇÃO primeiro: abrir o WhatsApp com a mensagem pronta. -->
        <UiButton
          :href="deepLink || undefined"
          target="_blank"
          rel="noopener"
          size="lg"
          icon="lucide:send"
          class="w-full justify-center"
          :disabled="!deepLink"
        >
          Abrir e enviar no WhatsApp
        </UiButton>

        <p class="text-center shop-meta" data-login-whatsapp-hint>
          Toque em enviar no WhatsApp. Você recebe um link e entra num toque.
        </p>

        <!-- Envio manual (fallback): código valorizado + copiar + abrir chat cru. -->
        <div v-if="code" class="rounded-lg border bg-card p-4 shop-stack-block" data-login-whatsapp-manual>
          <p class="shop-meta">
            Se o WhatsApp não abrir, envie o código abaixo diretamente para o nosso WhatsApp
            <span v-if="waNumberDisplay" class="whitespace-nowrap font-semibold">{{ waNumberDisplay }}</span>:
          </p>
          <div class="rounded-md border bg-background py-3 text-center font-mono text-xl font-semibold tracking-widest text-foreground">
            {{ code }}
          </div>
          <UiButton
            type="button"
            variant="outline"
            class="w-full justify-center"
            :icon="codeCopied ? 'lucide:check' : 'lucide:copy'"
            @click="copyCode"
          >
            {{ codeCopied ? 'Código copiado' : 'Copiar código' }}
          </UiButton>
          <UiButton
            :href="chatLink || undefined"
            target="_blank"
            rel="noopener"
            variant="outline"
            icon="lucide:message-circle"
            class="w-full justify-center"
            :disabled="!chatLink"
          >
            Abrir WhatsApp manualmente
          </UiButton>
        </div>
      </template>
    </div>

    <!-- Alternativas -->
    <div class="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
      <UiButton
        type="button"
        variant="ghost"
        size="sm"
        class="-ml-2 text-muted-foreground hover:text-foreground"
        icon="lucide:arrow-left"
        @click="emit('back')"
      >
        Voltar
      </UiButton>
      <UiButton
        type="button"
        variant="ghost"
        size="sm"
        class="text-muted-foreground hover:text-foreground"
        icon="lucide:smartphone"
        @click="emit('sms')"
      >
        Prefiro receber por SMS
      </UiButton>
    </div>
  </section>
</template>
