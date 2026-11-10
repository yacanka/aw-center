import { onBeforeUnmount, onMounted, readonly, ref, type DeepReadonly, type Ref } from 'vue'

/** Track a CSS media query without coupling feature components to window resize events. */
export function useMediaQuery(query: string): DeepReadonly<Ref<boolean>> {
  let mediaQuery = typeof window === 'undefined' ? null : window.matchMedia(query)
  const matches = ref(mediaQuery?.matches ?? false)

  function update(event?: MediaQueryListEvent): void {
    matches.value = event?.matches ?? mediaQuery?.matches ?? false
  }

  onMounted(() => {
    mediaQuery ??= window.matchMedia(query)
    update()
    mediaQuery.addEventListener('change', update)
  })

  onBeforeUnmount(() => mediaQuery?.removeEventListener('change', update))

  return readonly(matches)
}
