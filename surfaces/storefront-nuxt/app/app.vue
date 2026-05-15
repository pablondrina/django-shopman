<script setup lang="ts">
useHead({
  htmlAttrs: { lang: 'pt-BR' },
  link: [
    { rel: 'icon', href: '/favicon.ico' },
    { rel: 'manifest', href: '/manifest.json' }
  ],
  titleTemplate: (title?: string) => {
    if (!title || title === 'Shopman') return 'Shopman'
    if (title.endsWith(' — Shopman')) return title
    return `${title} — Shopman`
  }
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
