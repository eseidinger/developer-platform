import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/errors'
import { createGroup, getGovernance, getPolicy, IdempotentIntent, parseAccessResource, savePolicy } from './access-api'

const requests = vi.hoisted(() => ({ GET: vi.fn(), PUT: vi.fn(), POST: vi.fn() }))
vi.mock('@/api/client', () => ({ apiClient: requests }))
const base = { id: 'svc_test', name: 'reader', kind: 'service-access', project: 'consumer', state: 'active', version: 3, created_at: '2026-10-12T12:00:00Z', updated_at: '2026-10-12T12:01:00Z' }
afterEach(() => vi.resetAllMocks())
describe('access contract and redaction', () => {
  it('retains safe service metadata while removing credential values and extra nested fields', () => {
    const parsed = parseAccessResource('service-access', { ...base, client_secret: 'MUST-NOT-CACHE', spec: { providerProject: 'provider', application: 'provider', projectWideCredential: true, policyId: 'pol_test', principalId: 'prn_test', groups: ['grp_test'], credentials: [{ id: 'credential-version', state: 'active', secret: 'MUST-NOT-CACHE', token: 'MUST-NOT-CACHE' }], secretPrefix: 'ACCESS_ABC123', audience: 'app_test', providerUrl: 'https://api-provider.apps.test', clientSecret: 'MUST-NOT-CACHE' } })
    expect(JSON.stringify(parsed)).not.toContain('MUST-NOT-CACHE')
    expect(parsed.spec).toHaveProperty('secretPrefix', 'ACCESS_ABC123')
  })
  it('rejects malformed or mismatched envelopes without quoting the payload', () => {
    expect(() => parseAccessResource('group', { ...base, spec: { secret: 'MUST-NOT-RENDER' } })).toThrow('invalid application-access response')
  })
  it('recognizes only documented missing-resource responses as setup states', async () => {
    requests.GET.mockResolvedValueOnce({ error: { detail: 'Access policy is not configured' }, response: new Response(null, { status: 404 }) })
    await expect(getPolicy('provider')).resolves.toBeNull()
    requests.GET.mockResolvedValueOnce({ error: { detail: 'Unknown project' }, response: new Response(null, { status: 404 }) })
    await expect(getPolicy('provider')).rejects.toMatchObject({ status: 404 })
    requests.GET.mockResolvedValueOnce({ error: { detail: 'Access denied' }, response: new Response(null, { status: 403 }) })
    await expect(getGovernance('provider')).rejects.toMatchObject({ status: 403 })
    requests.GET.mockResolvedValueOnce({ error: { detail: 'Provider unavailable' }, response: new Response(null, { status: 503 }) })
    await expect(getGovernance('provider')).rejects.toMatchObject({ status: 503 })
  })
  it('preserves quoted versions and sends a create-only policy precondition', async () => {
    const put = requests.PUT.mockResolvedValue({ error: { detail: 'Changed' }, response: new Response(null, { status: 412 }) })
    const body = { component: 'api', defaultDecision: 'deny' as const, routes: [] }
    await expect(savePolicy('provider', body, 7)).rejects.toBeInstanceOf(ApiError)
    expect(put).toHaveBeenLastCalledWith('/v1/projects/{project}/applications/{application}/access-policy', expect.objectContaining({ params: { path: { project: 'provider', application: 'provider' }, header: { 'If-Match': '"7"' } } }))
    await expect(savePolicy('provider', body)).rejects.toMatchObject({ status: 412 })
    const options: unknown = put.mock.calls[1]?.[1]
    expect(options).toMatchObject({ params: { header: { 'If-Match': '"0"' } } })
  })
  it('does not echo validation inputs or secrets into errors', async () => {
    requests.POST.mockResolvedValue({ error: { detail: [{ input: 'MUST-NOT-RENDER' }] }, response: new Response(null, { status: 422 }) })
    await expect(createGroup('provider', { name: 'readers', displayName: 'Readers' }, 'key')).rejects.toMatchObject({ status: 422, message: 'The access settings were rejected. Check the fields and supported policy rules.' })
  })
  it('reuses an idempotency key for retries and replaces it when intent changes', () => {
    const intent = new IdempotentIntent(); const body = { name: 'readers', displayName: 'Readers' }
    const first = intent.keyFor(body)
    expect(intent.keyFor({ ...body })).toBe(first)
    expect(intent.keyFor({ ...body, displayName: 'Other readers' })).not.toBe(first)
  })
})
