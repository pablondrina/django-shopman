<script setup lang="ts">
const runtimeConfig = useRuntimeConfig()
const posSurfaceUrl = String(runtimeConfig.public.posSurfaceUrl || '/pos/')

useHead({ title: 'POS ativo' })

await navigateTo(posSurfaceUrl, { external: true, redirectCode: 302 })
</script>

<template>
  <UDashboardPanel id="pos-deprecated">
    <template #header>
      <UDashboardNavbar title="POS ativo" icon="i-lucide-shopping-bag">
        <template #leading>
          <UDashboardSidebarCollapse />
        </template>
      </UDashboardNavbar>
    </template>

    <template #body>
      <UContainer class="py-6">
        <UPageCard
          title="Abrindo POS ativo"
          description="Você será levado para a superfície operacional do POS."
          icon="i-lucide-route"
          variant="outline"
          spotlight
        >
          <template #footer>
            <div class="flex flex-wrap gap-2">
              <UButton
                :to="posSurfaceUrl"
                color="primary"
                icon="i-lucide-external-link"
                label="Abrir agora"
              />
              <UButton
                to="/"
                color="neutral"
                variant="outline"
                icon="i-lucide-layout-dashboard"
                label="Voltar ao Backstage"
              />
            </div>
          </template>
        </UPageCard>
      </UContainer>
    </template>
  </UDashboardPanel>
</template>
