import type { PolicyInput, RouteInput } from './access-api'

export const httpMethods = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'] as const
export function canonicalPath(path: string): boolean {
  if (!path.startsWith('/') || path.length > 2048 || /%(?![\da-f]{2})|%(?:2f|5c|25)/i.test(path)) return false
  try {
    const decoded = decodeURIComponent(path)
    return decoded === path && !/[\\?#]/.test(decoded) && ![...decoded].some((c) => c.charCodeAt(0) < 32 || c.charCodeAt(0) === 127) && !decoded.includes('//') &&
      !decoded.split('/').some((part) => part === '.' || part === '..') && !decoded.startsWith('/oauth2')
  } catch { return false }
}
function contains(route: RouteInput, path: string) {
  if (route.match.path != null) return route.match.path === path
  const prefix = (route.match.pathPrefix ?? '').replace(/\/+$/, '')
  return !prefix || path === prefix || path.startsWith(prefix + '/')
}
export function routesOverlap(left: RouteInput, right: RouteInput) {
  if (!left.match.methods.some((method) => right.match.methods.includes(method))) return false
  if (left.match.path != null) return contains(right, left.match.path)
  if (right.match.path != null) return contains(left, right.match.path)
  return contains(left, (right.match.pathPrefix ?? '').replace(/\/+$/, '') || '/') ||
    contains(right, (left.match.pathPrefix ?? '').replace(/\/+$/, '') || '/')
}
export function validatePolicy(policy: PolicyInput): string[] {
  const errors: string[] = []
  if (!policy.routes.length || policy.routes.length > 100) errors.push('Define between 1 and 100 route rules.')
  if (new Set(policy.routes.map((route) => route.name)).size !== policy.routes.length) errors.push('Route names must be unique.')
  for (const [index, route] of policy.routes.entries()) {
    const label = `Rule ${index + 1}`
    if (!route.name.trim() || route.name.length > 64) errors.push(`${label}: enter a name of 1–64 characters.`)
    if ((route.match.path != null) === (route.match.pathPrefix != null) || !canonicalPath(route.match.path ?? route.match.pathPrefix ?? '')) errors.push(`${label}: enter a canonical path outside /oauth2.`)
    if (!route.match.methods.length || new Set(route.match.methods).size !== route.match.methods.length) errors.push(`${label}: select unique HTTP methods.`)
    if (!route.authorization.anyOfGroups.length || route.authorization.anyOfGroups.length > 50 || new Set(route.authorization.anyOfGroups).size !== route.authorization.anyOfGroups.length) errors.push(`${label}: select between 1 and 50 unique groups.`)
    for (const other of policy.routes.slice(index + 1)) if (routesOverlap(route, other)) errors.push(`${label}: its path and methods overlap another rule.`)
  }
  const browser = policy.routes.filter((route) => route.authentication.mode === 'browser-session')
  if (browser.length && !browser.some((route) => route.match.methods.includes('GET'))) errors.push('Browser session rules need a GET entry route.')
  return errors
}
