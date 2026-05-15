<template>
  <div class="min-h-screen pb-[calc(var(--shop-bottom-nav-height)+1rem+env(safe-area-inset-bottom))] sm:pb-0">
    <AppHeader />
    <UMain>
      <slot />
    </UMain>
    <BottomCartBar />
    <ShopBottomTabs />
    <AppFooter />
    <ReorderConflictModal />
    <ReorderRecoveryModal />
    <CartIssueModal />
  </div>
</template>
