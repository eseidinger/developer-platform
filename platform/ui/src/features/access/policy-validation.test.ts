import { describe, expect, it } from 'vitest'
import type { PolicyInput, RouteInput } from './access-api'
import { canonicalPath, routesOverlap, validatePolicy } from './policy-validation'

const route = (path: string, prefix = true): RouteInput => ({ name: path, match: { ...(prefix ? { pathPrefix: path } : { path }), methods: ['GET'] }, authentication: { mode: 'bearer-token' }, authorization: { anyOfGroups: ['grp_a'] } })
const policy = (routes: RouteInput[]): PolicyInput => ({ component: 'api', defaultDecision: 'deny', routes })
describe('hosted policy validation', () => {
  it('matches complete segments, including the prefix base, and rejects overlap', () => {
    expect(routesOverlap(route('/api/'), route('/api', false))).toBe(true)
    expect(routesOverlap(route('/api'), route('/api/items', false))).toBe(true)
    expect(routesOverlap(route('/api'), route('/apiculture'))).toBe(false)
    expect(validatePolicy(policy([route('/api'), route('/api/items', false)]))).toContain('Rule 1: its path and methods overlap another rule.')
  })
  it('permits disjoint methods on an otherwise identical path', () => {
    const second = route('/api', false); second.name = 'write'; second.match.methods = ['POST']
    expect(validatePolicy(policy([route('/api'), second]))).toEqual([])
  })
  it.each(['/api/../secret', '/api/%2e%2e', '/api/%2fsecret', '/api/%5c', '/api/%252e', '/api//x', '/api\\x', '/api/%ZZ', '/api?x=1', '/oauth2/callback', '/oauth2-other', '/api/\u0000', '/api/caf%C3%A9'])('rejects ambiguous or noncanonical policy path %s', (path) => {
    expect(canonicalPath(path)).toBe(false)
  })
  it('allows canonical Unicode policy paths and the root prefix', () => {
    expect(canonicalPath('/api/café')).toBe(true)
    expect(canonicalPath('/')).toBe(true)
    expect(routesOverlap(route('/'), route('/assets'))).toBe(true)
  })
  it('requires groups, unique names/methods, and a browser GET entry', () => {
    const human = route('/app'); human.authentication.mode = 'browser-session'; human.match.methods = ['POST', 'POST']; human.authorization.anyOfGroups = []
    const errors = validatePolicy(policy([human, { ...human }]))
    expect(errors).toContain('Browser session rules need a GET entry route.')
    expect(errors).toContain('Route names must be unique.')
    expect(errors).toContain('Rule 1: select unique HTTP methods.')
    expect(errors).toContain('Rule 1: select between 1 and 50 unique groups.')
  })
})
