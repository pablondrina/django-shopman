<template>
  <div class="min-h-screen pb-36 sm:pb-24 lg:pb-0">
    <AppHeader />
    <UMain>
      <slot />
    </UMain>
    <BottomCartBar />
    <ShopBottomTabs />
    <AppFooter />
    <ReorderConflictModal />
  </div>
</template>
