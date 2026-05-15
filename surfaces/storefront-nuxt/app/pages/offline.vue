<script setup lang="ts">
useHead({ title: 'Offline' })
</script>

<template>
  <UContainer class="py-12 sm:py-16">
    <UPageCard
      title="Sem conexão"
      description="Não foi possível acessar a rede agora. Páginas já abertas podem continuar disponíveis, mas carrinho, checkout, pagamento e acompanhamento precisam de conexão."
      :ui="{ container: 'p-6 sm:p-8' }"
    >
      <div class="mt-6 flex flex-wrap gap-3">
        <UButton label="Tentar novamente" @click="reloadNuxtApp()" />
        <UButton label="Cardápio" to="/menu" color="neutral" variant="outline" />
      </div>
    </UPageCard>
  </UContainer>
</template>
