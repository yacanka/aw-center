import type { IUser } from '@/models/auth'

export interface AccessRule {
  staffOnly?: boolean
  anyPermissions?: string[]
  allPermissions?: string[]
}

export interface RouteAccessPolicy {
  public?: boolean
  allow?: AccessRule[]
}

export interface NavigationAccessItem<T> {
  key?: string | number
  type?: string
  children?: T[]
}

export type AccessDecision = 'allow' | 'login' | 'forbidden'

export const PUBLIC_ACCESS: RouteAccessPolicy = { public: true }
export const AUTHENTICATED_ACCESS: RouteAccessPolicy = {}

const NAVIGATION_POLICIES: Record<string, RouteAccessPolicy> = {
  '/users': {
    allow: [
      { anyPermissions: ['auth.view_user'] },
      { staffOnly: true, allPermissions: ['auth.add_user'] }
    ]
  },
  '/ddfAssistant': {
    allow: [{ anyPermissions: ['ddf.view_ddf', 'ddf.add_ddf'] }]
  },
  '/developer/doors': {
    allow: [{ staffOnly: true }]
  }
}

/** Return the granular access policy for a navigation path, or authenticated access by default. */
export function navigationAccessPolicy(path: string): RouteAccessPolicy {
  return NAVIGATION_POLICIES[path] || AUTHENTICATED_ACCESS
}

/** Resolve a route policy into an allow, login, or forbidden navigation decision. */
export function resolveRouteAccess(policy: RouteAccessPolicy, user: IUser | null): AccessDecision {
  if (policy.public) return 'allow'
  if (!user?.id || user.is_active === false) return 'login'
  if (!policy.allow?.length || user.is_superuser) return 'allow'
  return policy.allow.some((rule) => ruleAllowsUser(rule, user)) ? 'allow' : 'forbidden'
}

/** Check direct and group-derived Django permissions using an `app.codename` identifier. */
export function hasEffectivePermission(user: IUser, permissionName: string): boolean {
  if (user.is_superuser) return true
  const [appLabel, codename] = splitPermissionName(permissionName)
  if (!appLabel || !codename) return false
  return effectivePermissions(user).some(
    (permission) =>
      permission.content_type?.app_label === appLabel && permission.codename === codename
  )
}

/** Filter nested menu entries with the same policies enforced by the router. */
export function filterNavigationByAccess<T extends NavigationAccessItem<T>>(
  options: T[],
  user: IUser | null
): T[] {
  return options.flatMap((option) => filterNavigationOption(option, user))
}

/** Return a bounded internal post-login path and reject redirect loops or external targets. */
export function safePostLoginPath(value: unknown): string {
  if (typeof value !== 'string' || value.length > 500) return '/home'
  if (!value.startsWith('/') || value.startsWith('//') || /[\u0000-\u001f]/.test(value)) {
    return '/home'
  }
  const pathname = value.split(/[?#]/, 1)[0]
  return ['/login', '/invite', '/welcome', '/unauthorized'].includes(pathname) ? '/home' : value
}

function filterNavigationOption<T extends NavigationAccessItem<T>>(
  option: T,
  user: IUser | null
): T[] {
  if (option.type === 'divider') return [option]
  if (option.children) return filterNavigationGroup(option, user)
  if (typeof option.key !== 'string') return []
  const decision = resolveRouteAccess(navigationAccessPolicy(option.key), user)
  return decision === 'allow' ? [option] : []
}

function filterNavigationGroup<T extends NavigationAccessItem<T>>(
  option: T,
  user: IUser | null
): T[] {
  const children = filterNavigationByAccess(option.children || [], user)
  return children.length ? [{ ...option, children } as T] : []
}

function ruleAllowsUser(rule: AccessRule, user: IUser): boolean {
  if (rule.staffOnly && !user.is_staff) return false
  if (rule.allPermissions?.some((permission) => !hasEffectivePermission(user, permission))) {
    return false
  }
  if (!rule.anyPermissions?.length) return true
  return rule.anyPermissions.some((permission) => hasEffectivePermission(user, permission))
}

function effectivePermissions(user: IUser) {
  const groupPermissions = user.group_details?.flatMap((group) => group.permissions || []) || []
  return [...(user.permissions || []), ...groupPermissions]
}

function splitPermissionName(permissionName: string): [string, string] {
  const separatorIndex = permissionName.indexOf('.')
  if (separatorIndex <= 0) return ['', '']
  return [permissionName.slice(0, separatorIndex), permissionName.slice(separatorIndex + 1)]
}
