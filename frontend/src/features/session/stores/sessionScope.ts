import { getActivePinia, type Pinia, type PiniaPluginContext, type StoreGeneric } from 'pinia'

const storesByPinia = new WeakMap<Pinia, Set<StoreGeneric>>()

/** Track instantiated feature stores without importing their modules into the login entry graph. */
export function registerSessionScopedStore({ pinia, store }: PiniaPluginContext): void {
  if (store.$id === 'session') return
  let stores = storesByPinia.get(pinia)
  if (!stores) {
    stores = new Set<StoreGeneric>()
    storesByPinia.set(pinia, stores)
  }
  stores.add(store)
}

/** Clear only feature state instantiated for the current application/Pinia instance. */
export function resetSessionScopedStores(): void {
  const pinia = getActivePinia()
  if (!pinia) return
  storesByPinia.get(pinia)?.forEach((store) => store.$reset())
}
