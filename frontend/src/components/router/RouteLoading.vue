<template>
  <section class="route-loading-shell" aria-live="polite" aria-busy="true">
    <n-skeleton text width="35%" height="24px" />
    <n-skeleton text :repeat="3" />
    <n-skeleton height="240px" />
  </section>
</template>

<style scoped>
.route-loading-shell {
  display: grid;
  gap: 1rem;
  padding: 1.5rem;
}
</style>
