import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@/auth/auth-context'
import { ApiError } from '@/api/errors'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import * as api from './stores-api'

const box = 'space-y-4 rounded-xl border border-border bg-card p-5'
const field = 'block rounded-md border border-input bg-background px-3 py-2 text-sm'
type Action = (work: () => Promise<unknown>) => Promise<void>
function Form({ children, submit, disabled }: { children: ReactNode; submit: (data: FormData) => Promise<void>; disabled: boolean }) {
  function send(event: FormEvent<HTMLFormElement>) { event.preventDefault(); void submit(new FormData(event.currentTarget)) }
  return <form onSubmit={send}><fieldset disabled={disabled} className="flex flex-wrap items-end gap-3">{children}</fieldset></form>
}
const text = (data: FormData, key: string) => { const value = data.get(key); return typeof value === 'string' ? value : '' }
function Mode({ label = 'Access mode' }: { label?: string }) {
  return <label>{label}<select className={field} name="mode"><option value="read-only">Read-only</option><option value="read-write">Read-write, including schema changes</option></select></label>
}
export function StoresPage() {
  const { name } = useParams()
  const { status, user } = useAuth()
  if (status !== 'authenticated') return <section><h1 className="text-3xl font-semibold">Data stores</h1><p>Sign in to manage resources or use your human grants.</p></section>
  return <Workspace key={`${name ?? 'personal'}:${user?.profile.iss}:${user?.profile.sub}`} project={name} identity={`${user?.profile.iss}:${user?.profile.sub}`} />
}
function Workspace({ project, identity }: { project?: string; identity: string }) {
  const client = useQueryClient()
  const prefix = ['stores', identity, project ?? 'personal']
  const alive = useRef(true)
  const lock = useRef(false)
  const [busy, setBusy] = useState(false)
  const [uncertain, setUncertain] = useState(false)
  const [message, setMessage] = useState('')
  const [until, setUntil] = useState(() => Date.now() + 300_000)
  const context = useQuery({ queryKey: [...prefix, 'context'], queryFn: () => api.getContext(project!), enabled: Boolean(project) })
  const manage = Boolean(project && context.isSuccess && context.data?.manage)
  const interval = () => Date.now() < until ? 5000 : false as const
  const resources = useQuery({ queryKey: [...prefix, 'resources'], queryFn: () => api.getResources(project!), enabled: manage, refetchInterval: interval })
  const bindings = useQuery({ queryKey: [...prefix, 'bindings'], queryFn: () => api.getBindings(project!), enabled: manage, refetchInterval: interval })
  const mine = useQuery({ queryKey: [...prefix, 'mine'], queryFn: api.getMine, refetchInterval: interval })
  useEffect(() => { alive.current = true; return () => { alive.current = false; client.removeQueries({ queryKey: ['stores', identity, project ?? 'personal'] }) } }, [client, identity, project])
  async function refresh() {
    const results = await Promise.all([mine.refetch(), ...(project ? [context.refetch()] : []), ...(manage ? [resources.refetch(), bindings.refetch()] : [])])
    if (alive.current && results.every(r => !r.isError)) { setUncertain(false); setUntil(Date.now() + 300_000) }
    await client.invalidateQueries({ queryKey: [...prefix, 'grants'] })
    await client.invalidateQueries({ queryKey: [...prefix, 'leases'] })
  }
  const action: Action = async work => {
    if (lock.current || uncertain) return
    lock.current = true; setBusy(true); setMessage('')
    try { await work(); if (alive.current) { setMessage('Request accepted. Check the observed state for completion.'); await refresh() } }
    catch (error) { if (alive.current) { setMessage(error instanceof Error ? error.message : 'Request failed.'); if (!(error instanceof ApiError) || error.status >= 500 || error.status === 408) { setUncertain(true); setMessage('The request outcome may be unknown. Refresh and inspect the resource or lease history before retrying.') } } }
    finally { lock.current = false; if (alive.current) setBusy(false) }
  }
  const disabled = busy || uncertain
  const [confirm, setConfirm] = useState<{ title: string; detail: string; work: () => Promise<unknown> } | null>(null)
  const [confirmation, setConfirmation] = useState('')
  const [purge, setPurge] = useState<api.Preview | null>(null)
  const [keyText, setKeyText] = useState('')
  return <section className="max-w-5xl space-y-6"><Link to={project ? `/projects/${project}` : '/'} className="underline">{project ?? 'Projects'}</Link>
    <div className="flex items-center justify-between"><h1 className="text-3xl font-semibold">{project ? `${project} data stores` : 'My store access'}</h1><Button variant="outline" disabled={busy} onClick={() => void refresh()}>Refresh stores</Button></div>
    <p>Resources have an independent lifecycle. Removing an application retains its data. Each component needs an approved binding.</p>
    {message && <p role="status">{message}</p>}{uncertain && <p role="alert">Writes are paused until a successful refresh. Creation requests are never automatically retried.</p>}
    {project && context.isError && <p role="alert">{context.error.message}</p>}
    {manage && <><section className={box}><h2 className="text-xl font-semibold">Create resource</h2><Form disabled={disabled} submit={d => action(() => api.createResource(project!, { name: text(d, 'name'), provider: text(d, 'provider') as api.Provider, ...(text(d, 'provider') === 'qdrant' ? { configuration: { vector_size: Number(text(d, 'vectorSize')), distance: text(d, 'distance') as 'Cosine' | 'Dot' | 'Euclid' | 'Manhattan' } } : {}), quota_bytes: Number(text(d, 'quota')) * 1048576, extensions: text(d, 'provider') === 'postgresql' ? [...(d.has('vector') ? ['vector' as const] : []), ...(d.has('age') ? ['age' as const] : [])] : [] }))}>
      <label>Resource name<input className={field} name="name" required pattern="[a-z][a-z0-9-]*" maxLength={32} /></label>
      <label>Provider<select className={field} name="provider">{context.data?.providers.filter(p => p.enabled).map(p => <option key={p.id} value={p.id}>{p.id}</option>)}</select></label>
      <label>Storage allocation (MiB)<input className={field} name="quota" type="number" defaultValue={1024} min={1} required /></label><label><input type="checkbox" name="vector" /> pgvector (PostgreSQL)</label><label><input type="checkbox" name="age" /> AGE (PostgreSQL projection)</label><label>Qdrant vector dimensions<input className={field} name="vectorSize" type="number" defaultValue={384} min={1} max={65536} /></label><label>Qdrant distance<select className={field} name="distance">{['Cosine', 'Dot', 'Euclid', 'Manhattan'].map(value => <option key={value}>{value}</option>)}</select></label><Button type="submit">Create resource</Button></Form><p>AGE graphs must be rebuildable from protected sources and loaders. AGE-only changes may be lost during recovery.</p></section>
      {resources.isError && <p role="alert">{resources.error.message}</p>}{resources.isPending && <p role="status">Loading resources…</p>}
      {resources.data?.map(resource => <section className={box} key={resource.resource_id}><h2 className="text-xl font-semibold">{resource.name} · {resource.provider}</h2>
        <p>{resource.resource_id}</p><p>Desired: {resource.state} · observed: {resource.observed_state} · allocation: {resource.quota_bytes / 1048576} MiB{resource.error_code ? ` · ${resource.error_code}` : ''}</p>
        <p>Last measured usage: {resource.used_bytes == null ? 'unknown' : `${(resource.used_bytes / 1048576).toFixed(1)} MiB`}{resource.usage_measured_at ? ` at ${resource.usage_measured_at}` : ''}{resource.usage_error ? ' · latest measurement failed; previous reading may be stale' : ''}</p>
        {resource.state === 'purging' && <p>Permanent deletion waits until its intent is in a verified off-host backup. An operator can run the scheduled backup early; retained backup copies expire normally.</p>}
        {['postgresql', 'opensearch', 'qdrant'].includes(resource.provider) && <p>{resource.provider} byte quotas are advisory; monitoring and admission controls cannot guarantee a hard limit.</p>}
        {resource.provider === 'qdrant' && <p>Vector dimensions: {resource.configuration?.vector_size ?? 384} · distance: {resource.configuration?.distance ?? 'Cosine'}. This collection configuration is immutable.</p>}
        {resource.state === 'active' && <div className="space-y-3"><Form disabled={disabled} submit={d => action(() => api.renameResource(resource.resource_id, { name: text(d, 'name'), version: resource.version }))}><label>New name<input className={field} name="name" defaultValue={resource.name} required maxLength={32} /></label><Button type="submit" variant="outline">Rename</Button></Form>
          {context.data?.platform_admin && <Form disabled={disabled} submit={d => action(() => api.quota(resource.resource_id, { quota_bytes: Number(text(d, 'quota')) * 1048576, version: resource.version }))}><label>Approved allocation (MiB)<input className={field} name="quota" type="number" min={1} defaultValue={resource.quota_bytes / 1048576} required /></label><Button type="submit" variant="outline">Approve quota change</Button></Form>}
          <Button disabled={disabled} variant="outline" onClick={() => setConfirm({ title: 'Retire resource', detail: `${resource.name}: revoke every human and application grant and retain data.`, work: () => api.retireResource(resource.resource_id, resource.version) })}>Retire resource</Button></div>}
        {resource.state === 'retired' && resource.observed_state === 'retired' && <Button disabled={disabled} variant="destructive" onClick={() => void action(async () => { setPurge(await api.getPreview(resource.resource_id)); setConfirmation('') })}>Preview permanent purge</Button>}
        <Grants resource={resource} prefix={prefix} action={action} disabled={disabled} confirm={setConfirm} /></section>)}
      <section className={box}><h2 className="text-xl font-semibold">Component bindings</h2><p>Cross-project requests require the resource owner's approval. Copy an approved binding ID into that component's declaration.</p>
        <Form disabled={disabled} submit={d => action(() => api.requestBinding(project!, { resource_id: text(d, 'resource'), component: text(d, 'component'), mode: text(d, 'mode') as 'read-only' | 'read-write' }))}>
          <label>Resource UUID<input className={field} name="resource" required /></label><label>Component<input className={field} name="component" required /></label><Mode /><Button type="submit">Request binding</Button></Form>
        {bindings.isError && <p role="alert">{bindings.error.message}</p>}{bindings.data?.map(g => <div key={g.grant_id} className="space-y-2 border-t pt-3"><p>{g.component} → {g.resource_id} · {g.mode} · {g.state} / {g.observed_state}</p><code>{JSON.stringify({ bindings: [{ bindingId: g.grant_id, envPrefix: '' }] })}</code>
          {g.state === 'active' && <Button disabled={disabled} variant="outline" onClick={() => setConfirm({ title: 'Revoke binding', detail: `${g.component}: end this component's data access and retain resource data.`, work: () => api.revoke(g) })}>Revoke binding</Button>}</div>)}</section></>}
    <section className={box}><h2 className="text-xl font-semibold">My private and console access</h2><p>Human credentials last 24 hours. Active connections close at expiry. Renew early and reconnect; your old lease keeps its original deadline.</p>
      <Form disabled={disabled} submit={d => { setKeyText(text(d, 'key')); setConfirm({ title: 'Replace SSH key', detail: 'Register this key and end your existing store credential leases. Issue fresh credentials afterward.', work: () => api.key(text(d, 'key')) }); return Promise.resolve() }}><label>Ed25519 public key<textarea className={field} name="key" required autoComplete="off" /></label><Button type="submit" variant="outline">Replace SSH key</Button></Form>
      {mine.isError && <p role="alert">{mine.error.message}</p>}{mine.isPending && <p role="status">Loading your grants…</p>}
      {mine.data?.filter(row => !project || row.resource.owner_project === project).map(row => <HumanAccess key={row.grant.grant_id} grant={row.grant} resource={row.resource} prefix={prefix} action={action} disabled={disabled} />)}
      {mine.isSuccess && mine.data.length === 0 && <p>No named-resource human grants. An administrator must grant access explicitly.</p>}</section>
    <Dialog open={Boolean(confirm)} onOpenChange={open => { if (!open && !busy) { setConfirm(null); setKeyText('') } }}><DialogContent><DialogTitle>{confirm?.title}</DialogTitle><DialogDescription>{confirm?.detail}</DialogDescription>{keyText && <p>New public key will replace the previous key.</p>}<div className="flex gap-2"><Button variant="outline" disabled={busy} onClick={() => { setConfirm(null); setKeyText('') }}>Cancel</Button><Button disabled={disabled} onClick={() => { const pending = confirm; setConfirm(null); setKeyText(''); if (pending) void action(pending.work) }}>Confirm</Button></div></DialogContent></Dialog>
    <Dialog open={Boolean(purge)} onOpenChange={open => { if (!open && !busy) { setPurge(null); setConfirmation('') } }}><DialogContent><DialogTitle>Permanently purge resource</DialogTitle><DialogDescription>{purge?.name} · {purge?.owner_project} · {purge?.effect}</DialogDescription><label>Type resource UUID to confirm<input className={field} value={confirmation} onChange={e => setConfirmation(e.target.value)} autoComplete="off" /></label><p>{purge?.resource_id}</p><Button disabled={disabled || confirmation !== purge?.resource_id} variant="destructive" onClick={() => { const pending = purge; setPurge(null); setConfirmation(''); if (pending) void action(() => api.purgeResource(pending)) }}>Permanently purge</Button></DialogContent></Dialog>
  </section>
}
function Grants({ resource, prefix, action, disabled, confirm }: { resource: api.Resource; prefix: string[]; action: Action; disabled: boolean; confirm: (value: { title: string; detail: string; work: () => Promise<unknown> }) => void }) {
  const query = useQuery({ queryKey: [...prefix, 'grants', resource.resource_id], queryFn: () => api.getGrants(resource.resource_id) })
  return <div className="space-y-3"><h3 className="font-semibold">Human grants and incoming bindings</h3>
    {resource.state === 'active' && <Form disabled={disabled} submit={d => action(() => api.createHuman(resource.resource_id, { issuer: text(d, 'issuer'), subject: text(d, 'subject'), mode: text(d, 'mode') as 'read-only' | 'read-write' }))}><label>Issuer<input className={field} name="issuer" type="url" required /></label><label>Subject ID<input className={field} name="subject" required /></label><Mode /><Button type="submit">Grant human access</Button></Form>}
    {query.isError && <p role="alert">{query.error.message}</p>}{query.data?.map(g => <div key={g.grant_id} className="space-y-2 border-t pt-3"><p>{g.kind === 'human' ? `${g.issuer} / ${g.subject}` : `${g.consumer_project} / ${g.component}`} · {g.mode} · {g.state} / {g.observed_state}{g.error_code ? ` · ${g.error_code}` : ''}</p>
      {g.state === 'pending' && <><Button disabled={disabled} onClick={() => confirm({ title: 'Approve cross-project binding', detail: `${g.consumer_project}/${g.component} requests ${g.mode} access to ${resource.name}.`, work: () => api.approve(g, true) })}>Review approval</Button><Button disabled={disabled} variant="outline" onClick={() => void action(() => api.approve(g, false))}>Reject</Button></>}
      {g.state === 'active' && <><Button disabled={disabled} variant="outline" onClick={() => confirm({ title: 'Change resource permissions', detail: `Change ${g.kind} grant to ${g.mode === 'read-only' ? 'read-write with schema changes' : 'read-only'}. Existing credential generations will be revoked.`, work: () => api.mode(g, g.mode === 'read-only' ? 'read-write' : 'read-only') })}>Change permissions</Button><Button disabled={disabled} variant="outline" onClick={() => confirm({ title: 'Revoke resource grant', detail: 'End every credential generation and active connection for this grant. Retain data.', work: () => api.revoke(g) })}>Revoke grant</Button></>}
    </div>)}</div>
}
function HumanAccess({ grant, resource, prefix, action, disabled }: { grant: api.Grant; resource: api.Resource; prefix: string[]; action: Action; disabled: boolean }) {
  const client = useQueryClient()
  const [credential, setCredential] = useState<api.Credential | null>(null)
  const [shown, setShown] = useState(false)
  const alive = useRef(true)
  useEffect(() => { alive.current = true; return () => { alive.current = false } }, [])
  useEffect(() => {
    if (!credential) return
    const timeout = window.setTimeout(() => { setCredential(null); setShown(false) }, Math.max(0, Date.parse(credential.expires_at) - Date.now()))
    return () => window.clearTimeout(timeout)
  }, [credential])
  const history = useQuery({ queryKey: [...prefix, 'leases', grant.grant_id], queryFn: () => api.leases(grant.grant_id) })
  async function openConsole(id: string) {
    const launch = await api.launchConsole(id)
    if (!alive.current) return
    const form = document.createElement('form')
    form.method = 'POST'; form.action = launch.url; form.target = '_blank'; form.rel = 'noopener noreferrer'
    const input = document.createElement('input')
    input.type = 'hidden'; input.name = 'launch'; input.value = launch.launch
    form.append(input); document.body.append(form)
    try { form.submit() } finally { input.value = ''; form.remove() }
  }
  async function reveal(id: string) { const value = await api.reveal(id); if (alive.current) { setCredential(value); setShown(false) } }
  return <div className="space-y-3 border-t pt-3"><h3 className="font-semibold">{resource.owner_project} / {resource.name} · {grant.mode}</h3><p>{resource.provider} · {resource.resource_id}</p>
    <Button disabled={disabled} onClick={() => void action(async () => { const issued = await api.issue(grant.grant_id); if (alive.current) setCredential(issued); await client.invalidateQueries({ queryKey: [...prefix, 'leases', grant.grant_id] }) })}>Issue 24-hour credential</Button>
    {history.isError && <p role="alert">{history.error.message}</p>}{history.data?.filter(c => c.state !== 'revoked').map(c => <div key={c.credential_id}><p>{c.credential_id} · {c.state} · expires {c.expires_at}</p><Button disabled={disabled} variant="outline" onClick={() => void action(() => reveal(c.credential_id))}>Inspect this lease</Button></div>)}
    {credential && <div className="space-y-3 rounded border p-3"><p>Lease {credential.credential_id} · {credential.state} · expires {credential.expires_at}</p>
      {!credential.connection ? <><p>Credential provisioning is pending. Inspect this lease again; do not issue another one.</p><Button disabled={disabled} onClick={() => void action(() => reveal(credential.credential_id))}>Check credential readiness</Button></> : <>
        {!credential.ssh && <p>The operator has not advertised a remote SSH bastion. {resource.console_url ? 'Use the available console or ask for a private native-client entry point.' : 'Ask the operator for the private native-client entry point.'}</p>}
        {credential.ssh && <><p>Start a private tunnel, then connect your native client to localhost:15432. For HTTP stores, replace the endpoint host and port with http://127.0.0.1:15432; retain the scoped credential and resource identifier.</p><code className="block break-all">ssh -N -p {credential.ssh.port} -L 15432:{credential.ssh.destination}:{credential.ssh.destination_port} {credential.ssh.user}@{credential.ssh.host}</code></>}
        {Object.entries(credential.connection).map(([key, value]) => <label className="block" key={key}>{key}<input className={field} readOnly type={!shown && /PASS|SECRET|TOKEN|KEY/.test(key) ? 'password' : 'text'} value={value} autoComplete="off" /></label>)}
        <Button variant="outline" onClick={() => setShown(!shown)}>{shown ? 'Hide credential values' : 'Reveal credential values'}</Button>
        {['s3', 'qdrant'].includes(resource.provider) && resource.console_url && <><p>Open the official console, then use {resource.provider === 's3' ? 'RUSTFS_CONSOLE_ACCESS_KEY and RUSTFS_CONSOLE_SECRET_KEY' : 'QDRANT_API_KEY'} from this human credential for its separate native login. The console is limited to this lease and closes data access at expiry. Saved values belong to this browser profile; clear the console's site data when finished on a shared device.</p><Button disabled={disabled} variant="outline" onClick={() => void action(() => openConsole(credential.credential_id))}>Open {resource.provider === 's3' ? 'RustFS' : 'Qdrant'} console</Button></>}
        {resource.provider === 'postgresql' && resource.console_url && <><p>For browser access, sign in to pgAdmin, register host store-access and the PGPORT lease port shown above. Set Maintenance database to PGDATABASE, Username to PGUSER, and SSL mode to Disable; use your own PGPASSWORD. Do not register the raw PostgreSQL host. Native SSL is disabled inside the encrypted SSH tunnel or isolated console network.</p><a className="underline" href={resource.console_url} target="_blank" rel="noopener noreferrer">Open PostgreSQL console</a></>}
      </>}
      <Button variant="outline" onClick={() => { setCredential(null); setShown(false) }}>Close and discard credential</Button></div>}
  </div>
}
