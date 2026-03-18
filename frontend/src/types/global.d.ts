import { useDccStore, useAuthStore, useDdfStore, useCompdocStore, useDocproofStore, useDoorsStore, useOrgsStore } from '@/stores/api'
import { useUserStore } from '@/stores/user'

declare global {
  interface Window {
    $message: import("naive-ui").MessageApi
    $dialog: import("naive-ui").DialogApi
    $notification: import("naive-ui").NotificationApi
    $loadingBar: import("naive-ui").LoadingBarApi
    $dccStore: ReturnType<typeof useDccStore>
    $compdocStore: ReturnType<typeof useCompdocStore>
    $authStore: ReturnType<typeof useAuthStore>
    $ddfStore: ReturnType<typeof useDdfStore>
    $orgsStore: ReturnType<typeof useOrgsStore>
    $userStore: ReturnType<typeof useUserStore>
  }
}

export { }
