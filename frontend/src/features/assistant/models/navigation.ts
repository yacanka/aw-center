import type { Router } from 'vue-router'

/** Resolve only an exact internal registered route; aliases and redirects are not targets. */
export function resolveAssistantPath(path: string, router: Router): string | null {
  if (
    typeof path !== 'string' ||
    path.length > 200 ||
    !/^\/[A-Za-z0-9/_-]+$/.test(path) ||
    path.includes('//') ||
    path.endsWith('/')
  )
    return null
  const resolved = router.resolve(path)
  if (!resolved.matched.length || resolved.path !== path) return null
  if (resolved.matched.some((record) => record.redirect || record.aliasOf)) return null
  const target = resolved.matched.at(-1)
  if (!target || target.path.includes('pathMatch')) return null
  return path
}
