import 'vue-router'
import type { RouteAccessPolicy } from '@/features/session/services/accessPolicy'

declare module 'vue-router' {
  interface RouteMeta {
    public?: boolean
    access?: RouteAccessPolicy
  }
}

export {}
