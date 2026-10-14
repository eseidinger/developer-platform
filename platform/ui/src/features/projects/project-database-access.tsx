import * as React from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { ApiError } from '@/api/errors'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  createHumanDatabaseGrant, getMyDatabaseAccess, issueMyDatabaseCredential,
  listHumanDatabaseGrants, replaceMyDatabaseKey, revokeHumanDatabaseGrant,
  type HumanDatabaseGrant, type NewHumanDatabaseGrant, type OneTimeDatabaseCredential,
} from './database-access-api'

function expectedAbsence(error: unknown, status: number) {
  return error instanceof ApiError && error.status === status
}

function ProjectDatabaseAccess({ name, enabled }: { name: string; enabled: boolean }) {
  const mine = useQuery({ queryKey: ['projects', name, 'database-access', 'me'], queryFn: () => getMyDatabaseAccess(name), enabled, retry: false })
  const grants = useQuery({ queryKey: ['projects', name, 'database-access', 'grants'], queryFn: () => listHumanDatabaseGrants(name), enabled, retry: false })
  const [creating, setCreating] = React.useState(false)
  const [revoking, setRevoking] = React.useState<HumanDatabaseGrant | null>(null)
  const [replacingKey, setReplacingKey] = React.useState(false)
  const [issuing, setIssuing] = React.useState(false)

  if (!enabled) return null

  return <section aria-labelledby="database-access-title" className="rounded-xl border border-border bg-card p-6 shadow-sm">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h2 id="database-access-title" className="text-lg font-medium">Human database access</h2>
        <p className="mt-1 text-sm text-muted-foreground">Read-only PostgreSQL identities are separate from application credentials. The API enforces every grant and revocation.</p>
      </div>
      {grants.data && <Button variant="outline" onClick={() => setCreating(true)}>Grant database access</Button>}
    </div>

    {mine.isLoading && <p role="status" className="mt-4 text-sm text-muted-foreground">Loading your database access…</p>}
    {mine.isError && !expectedAbsence(mine.error, 404) && !expectedAbsence(mine.error, 403) && <p role="alert" className="mt-4 text-sm text-destructive">{mine.error.message}</p>}
    {mine.data ? <div className="mt-4 rounded-lg border border-border p-4 text-sm">
      <h3 className="font-medium">Your database identity</h3>
      <dl className="mt-2 grid gap-2 sm:grid-cols-2">
        <div><dt className="text-muted-foreground">Database</dt><dd className="break-all font-mono">{mine.data.database}</dd></div>
        <div><dt className="text-muted-foreground">SQL username</dt><dd className="break-all font-mono">{mine.data.username}</dd></div>
        <div><dt className="text-muted-foreground">SSH account</dt><dd className="font-mono">{mine.data.sshUser}</dd></div>
        <div><dt className="text-muted-foreground">Key fingerprint</dt><dd className="break-all font-mono">{mine.data.keyFingerprint}</dd></div>
      </dl>
      <p className="mt-3 text-xs text-muted-foreground">Use the operator-provided bastion host, port, and verified host key. The tunnel is configured outside this portal.</p>
      <div className="mt-3 flex flex-wrap gap-2"><Button size="sm" variant="outline" onClick={() => setReplacingKey(true)}>Replace SSH key</Button><Button size="sm" variant="outline" onClick={() => setIssuing(true)}>Rotate SQL password</Button></div>
    </div> : !mine.isLoading && (expectedAbsence(mine.error, 404) || mine.isSuccess) && <p className="mt-4 text-sm text-muted-foreground">You do not have a personal database grant for this project.</p>}

    {grants.isLoading && <p role="status" className="mt-4 text-sm text-muted-foreground">Loading database grants…</p>}
    {grants.isError && !expectedAbsence(grants.error, 403) && <p role="alert" className="mt-4 text-sm text-destructive">{grants.error.message}</p>}
    {grants.data && <div className="mt-5">
      <h3 className="font-medium">Project database grants</h3>
      {grants.data.length ? <ul className="mt-3 divide-y divide-border rounded-lg border border-border text-sm">{grants.data.map((grant) => <li key={`${grant.issuer}|${grant.subject}`} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
        <div><p className="font-medium break-all">{grant.subject} <span className="text-muted-foreground">· {grant.active ? 'active' : 'revoked'}</span></p><p className="text-xs text-muted-foreground break-all">{grant.issuer}</p><p className="mt-1 text-xs text-muted-foreground break-all">{grant.username} · {grant.keyFingerprint}</p></div>
        {grant.active && <Button size="sm" variant="destructive" onClick={() => setRevoking(grant)}>Revoke</Button>}
      </li>)}</ul> : <p className="mt-2 text-sm text-muted-foreground">No human database grants are recorded.</p>}
    </div>}

    {creating && <CreateDatabaseGrantDialog name={name} onClose={() => setCreating(false)} />}
    {revoking && <RevokeDatabaseGrantDialog name={name} grant={revoking} onClose={() => setRevoking(null)} />}
    {replacingKey && <ReplaceDatabaseKeyDialog name={name} onClose={() => setReplacingKey(false)} />}
    {issuing && <IssueDatabaseCredentialDialog name={name} onClose={() => setIssuing(false)} />}
  </section>
}

function CreateDatabaseGrantDialog({ name, onClose }: { name: string; onClose: () => void }) {
  const [draft, setDraft] = React.useState<NewHumanDatabaseGrant>({ issuer: '', subject: '', publicKey: '' })
  const queryClient = useQueryClient()
  const create = useMutation({ mutationFn: () => createHumanDatabaseGrant(name, draft), onSuccess: async () => {
    await queryClient.invalidateQueries({ queryKey: ['projects', name, 'database-access'] })
    onClose()
  } })
  const valid = Boolean(draft.issuer.trim() && draft.subject.trim() && draft.publicKey.trim())
  return <Dialog open onOpenChange={(open) => { if (!open && !create.isPending) onClose() }}><DialogContent className="sm:max-w-xl" showCloseButton={!create.isPending}><DialogHeader><DialogTitle>Grant human database access</DialogTitle><DialogDescription>Enter the human’s exact OIDC issuer and subject and their bare ssh-ed25519 public key. This creates a separate read-only SQL login; no password is shown to the administrator.</DialogDescription></DialogHeader><form className="space-y-4" onSubmit={(event) => { event.preventDefault(); if (valid) create.mutate() }}><div className="space-y-2"><Label htmlFor="database-grant-issuer">Issuer</Label><Input id="database-grant-issuer" autoComplete="off" maxLength={2048} value={draft.issuer} disabled={create.isPending} onChange={(event) => setDraft({ ...draft, issuer: event.target.value })} /></div><div className="space-y-2"><Label htmlFor="database-grant-subject">Subject ID</Label><Input id="database-grant-subject" autoComplete="off" maxLength={1024} value={draft.subject} disabled={create.isPending} onChange={(event) => setDraft({ ...draft, subject: event.target.value })} /></div><div className="space-y-2"><Label htmlFor="database-grant-key">SSH public key</Label><textarea id="database-grant-key" className="min-h-20 w-full rounded-lg border border-input bg-transparent px-3 py-2 font-mono text-xs" autoComplete="off" spellCheck={false} maxLength={256} value={draft.publicKey} disabled={create.isPending} onChange={(event) => setDraft({ ...draft, publicKey: event.target.value })} /></div>{create.isError && <p role="alert" className="text-sm text-destructive">{create.error.message}</p>}<DialogFooter><Button type="button" variant="outline" disabled={create.isPending} onClick={onClose}>Cancel</Button><Button type="submit" disabled={!valid || create.isPending}>{create.isPending ? 'Granting…' : 'Grant access'}</Button></DialogFooter></form></DialogContent></Dialog>
}

function RevokeDatabaseGrantDialog({ name, grant, onClose }: { name: string; grant: HumanDatabaseGrant; onClose: () => void }) {
  const queryClient = useQueryClient()
  const revoke = useMutation({ mutationFn: () => revokeHumanDatabaseGrant(name, grant), onSuccess: async () => {
    await queryClient.invalidateQueries({ queryKey: ['projects', name, 'database-access'] })
    onClose()
  } })
  return <Dialog open onOpenChange={(open) => { if (!open && !revoke.isPending) onClose() }}><DialogContent showCloseButton={!revoke.isPending}><DialogHeader><DialogTitle>Revoke database access</DialogTitle><DialogDescription>Revoke {grant.subject} from {name}? The SQL login is disabled and active PostgreSQL sessions for this role are terminated. Existing SSH tunnels may remain connected but cannot use this role.</DialogDescription></DialogHeader>{revoke.isError && <p role="alert" className="text-sm text-destructive">{revoke.error.message}</p>}<DialogFooter><Button type="button" variant="outline" disabled={revoke.isPending} onClick={onClose}>Cancel</Button><Button type="button" variant="destructive" disabled={revoke.isPending} onClick={() => revoke.mutate()}>{revoke.isPending ? 'Revoking…' : 'Revoke access'}</Button></DialogFooter></DialogContent></Dialog>
}

function ReplaceDatabaseKeyDialog({ name, onClose }: { name: string; onClose: () => void }) {
  const [publicKey, setPublicKey] = React.useState('')
  const queryClient = useQueryClient()
  const replace = useMutation({ mutationFn: () => replaceMyDatabaseKey(name, publicKey.trim()), onSuccess: async () => {
    await queryClient.invalidateQueries({ queryKey: ['projects', name, 'database-access'] })
    onClose()
  } })
  return <Dialog open onOpenChange={(open) => { if (!open && !replace.isPending) onClose() }}><DialogContent className="sm:max-w-xl" showCloseButton={!replace.isPending}><DialogHeader><DialogTitle>Replace your SSH key</DialogTitle><DialogDescription>Paste a bare ssh-ed25519 public key. The previous key stops authorizing new tunnel connections when no other active grant uses it.</DialogDescription></DialogHeader><form className="space-y-4" onSubmit={(event) => { event.preventDefault(); if (publicKey.trim()) replace.mutate() }}><div className="space-y-2"><Label htmlFor="database-replacement-key">New SSH public key</Label><textarea id="database-replacement-key" className="min-h-20 w-full rounded-lg border border-input bg-transparent px-3 py-2 font-mono text-xs" autoComplete="off" spellCheck={false} maxLength={256} value={publicKey} disabled={replace.isPending} onChange={(event) => setPublicKey(event.target.value)} /></div>{replace.isError && <p role="alert" className="text-sm text-destructive">{replace.error.message}</p>}<DialogFooter><Button type="button" variant="outline" disabled={replace.isPending} onClick={onClose}>Cancel</Button><Button type="submit" disabled={!publicKey.trim() || replace.isPending}>{replace.isPending ? 'Replacing…' : 'Replace key'}</Button></DialogFooter></form></DialogContent></Dialog>
}

function IssueDatabaseCredentialDialog({ name, onClose }: { name: string; onClose: () => void }) {
  const [result, setResult] = React.useState<OneTimeDatabaseCredential | null>(null)
  const [error, setError] = React.useState<string | null>(null)
  const [isIssuing, setIsIssuing] = React.useState(false)
  const [visible, setVisible] = React.useState(false)

  function close() {
    if (isIssuing) return
    setResult(null)
    setError(null)
    setVisible(false)
    onClose()
  }

  async function issue() {
    if (isIssuing || result) return
    setIsIssuing(true)
    setError(null)
    try {
      setResult(await issueMyDatabaseCredential(name))
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not rotate the database password.')
    } finally {
      setIsIssuing(false)
    }
  }

  async function copyPassword() {
    if (!result) return
    try { await navigator.clipboard.writeText(result.password) } catch { setError('Copy failed. Reveal and copy the password manually.') }
  }

  return <Dialog open onOpenChange={(open) => { if (!open) close() }}><DialogContent className="sm:max-w-xl" showCloseButton={!isIssuing}><DialogHeader><DialogTitle>{result ? 'Save your database password' : 'Rotate your SQL password'}</DialogTitle><DialogDescription>{result ? 'This password is shown once. Store it in a protected password manager before closing; the portal will discard it.' : 'This replaces the password for new SQL connections. Existing database sessions remain until they close or your grant is revoked.'}</DialogDescription></DialogHeader>{result ? <div className="space-y-4"><dl className="grid gap-2 text-sm"><div><dt className="text-muted-foreground">Database</dt><dd className="break-all font-mono">{result.database}</dd></div><div><dt className="text-muted-foreground">Username</dt><dd className="break-all font-mono">{result.username}</dd></div></dl><div className="space-y-2"><Label htmlFor="database-onetime-password">One-time password</Label><div className="flex gap-2"><Input id="database-onetime-password" readOnly type={visible ? 'text' : 'password'} value={result.password} autoComplete="off" /><Button type="button" variant="outline" onClick={() => setVisible(!visible)}>{visible ? 'Hide' : 'Reveal'}</Button><Button type="button" variant="outline" onClick={() => void copyPassword()}>Copy</Button></div></div>{error && <p role="alert" className="text-sm text-destructive">{error}</p>}<DialogFooter><Button type="button" onClick={close}>I saved the password</Button></DialogFooter></div> : <div className="space-y-4">{error && <p role="alert" className="text-sm text-destructive">{error}</p>}<DialogFooter><Button type="button" variant="outline" disabled={isIssuing} onClick={close}>Cancel</Button><Button type="button" disabled={isIssuing} onClick={() => void issue()}>{isIssuing ? 'Rotating…' : 'Rotate password'}</Button></DialogFooter></div>}</DialogContent></Dialog>
}

export { ProjectDatabaseAccess }
