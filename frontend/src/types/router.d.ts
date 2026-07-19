import 'vue-router'
import type { RouteAccessPolicy } from '@/services/accessPolicy'

declare module 'vue-router' {
  interface RouteMeta {
    public?: boolean
    access?: RouteAccessPolicy
  }
}

export {}
