<script setup lang="ts">
useHead({
  htmlAttrs: { lang: 'pt-BR' },
  link: [{ rel: 'icon', href: '/favicon.ico' }]
})

useSeoMeta({
  titleTemplate: '%s — Shopman'
})
</script>

<template>
  <UApp>
    <NuxtLoadingIndicator />
    <NuxtLayout>
      <NuxtPage />
    </NuxtLayout>
  </UApp>
</template>
