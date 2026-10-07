import * as React from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { ApiError } from '@/api/errors'
import { useAuth } from '@/auth/auth-context'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { deletePlatformGrant, getPlatformGrants, putPlatformGrant, type PlatformGrant } from '@/features/projects/projects-api'

type PlatformGrantDraft = Omit<PlatformGrant, 'grantedAt' | 'role'>

function PlatformAdministrationPage() {
  const { status, user } = useAuth()
  const grants = useQuery({ queryKey: ['platform', 'grants'], queryFn: getPlatformGrants, enabled: status === 'authenticated' })
  const [granting, setGranting] = React.useState(false)
  const [revoking, setRevoking] = React.useState<PlatformGrant | null>(null)
  const issuer = typeof user?.profile.iss === 'string' ? user.profile.iss : null
  const subject = typeof user?.profile.sub === 'string' ? user.profile.sub : null

  if (status !== 'authenticated') return <section><h1 className="text-3xl font-semibold tracking-tight">Platform administration</h1><p className="mt-2 text-muted-foreground">Sign in to inspect platform administration access.</p></section>
  if (grants.isLoading) return <section><h1 className="text-3xl font-semibold tracking-tight">Platform administration</h1><p role="status" className="mt-2 text-muted-foreground">Loading platform grants…</p></section>
  if (grants.isError && grants.error instanceof ApiError && grants.error.status === 403) return <section><h1 className="text-3xl font-semibold tracking-tight">Platform administration</h1><p className="mt-2 text-muted-foreground">Your current platform access does not allow administration changes.</p></section>
  if (grants.isError) return <section><h1 className="text-3xl font-semibold tracking-tight">Platform administration</h1><p role="alert" className="mt-2 text-destructive">{grants.error.message}</p></section>

  return <section aria-labelledby="platform-admin-title" className="max-w-3xl space-y-6"><div className="space-y-2"><h1 id="platform-admin-title" className="text-3xl font-semibold tracking-tight">Platform administration</h1><p className="text-muted-foreground">Platform administrators can create or revoke platform-administrator access. The API enforces every action; this screen does not grant authority itself.</p></div><section aria-labelledby="platform-grants-title" className="rounded-xl border border-border bg-card p-6 shadow-sm"><div className="flex flex-wrap items-center justify-between gap-3"><div><h2 id="platform-grants-title" className="text-lg font-medium">Platform administrators</h2><p className="mt-1 text-sm text-muted-foreground">Grant only to trusted operators. You cannot revoke your own platform access here or through the API.</p></div><Button onClick={() => setGranting(true)}>Grant platform access</Button></div>{grants.data?.length ? <ul className="mt-4 divide-y divide-border rounded-lg border border-border text-sm">{grants.data.map((grant) => { const isSelf = grant.issuer === issuer && grant.subject === subject; return <li key={`${grant.issuer}|${grant.subject}`} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3"><div><p className="font-medium">{grant.displayName ?? grant.subject}{isSelf ? ' (you)' : ''}</p><p className="text-xs text-muted-foreground break-all">{grant.issuer} · {grant.subject}</p><p className="mt-1 text-xs text-muted-foreground">Granted {new Date(grant.grantedAt).toLocaleString()}</p></div>{isSelf ? <span className="text-xs text-muted-foreground">Your access</span> : <Button size="sm" variant="destructive" onClick={() => setRevoking(grant)}>Revoke</Button>}</li> })}</ul> : <p className="mt-3 text-sm text-muted-foreground">No platform grants are recorded.</p>}</section>{granting && <GrantPlatformAccessDialog onClose={() => setGranting(false)} />}{revoking && <RevokePlatformAccessDialog grant={revoking} onClose={() => setRevoking(null)} />}</section>
}

function GrantPlatformAccessDialog({ onClose }: { onClose: () => void }) {
  const [draft, setDraft] = React.useState<PlatformGrantDraft>({ issuer: '', subject: '', displayName: null })
  const queryClient = useQueryClient()
  const grant = useMutation({ mutationFn: () => putPlatformGrant(draft), onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: ['platform', 'grants'] }); onClose() } })
  const valid = Boolean(draft.issuer.trim() && draft.subject.trim())
  return <Dialog open onOpenChange={(open) => { if (!open && !grant.isPending) onClose() }}><DialogContent><DialogHeader><DialogTitle>Grant platform access</DialogTitle><DialogDescription>Enter the recipient identity from the configured identity provider. This gives platform-administrator access across all projects.</DialogDescription></DialogHeader><form className="space-y-4" onSubmit={(event) => { event.preventDefault(); if (valid) grant.mutate() }}><div className="space-y-2"><Label htmlFor="platform-grant-issuer">Issuer</Label><Input id="platform-grant-issuer" autoComplete="off" value={draft.issuer} disabled={grant.isPending} onChange={(event) => setDraft({ ...draft, issuer: event.target.value })} /></div><div className="space-y-2"><Label htmlFor="platform-grant-subject">Subject ID</Label><Input id="platform-grant-subject" autoComplete="off" value={draft.subject} disabled={grant.isPending} onChange={(event) => setDraft({ ...draft, subject: event.target.value })} /></div><div className="space-y-2"><Label htmlFor="platform-grant-display-name">Display name (optional)</Label><Input id="platform-grant-display-name" autoComplete="off" value={draft.displayName ?? ''} disabled={grant.isPending} onChange={(event) => setDraft({ ...draft, displayName: event.target.value || null })} /></div>{grant.isError && <p role="alert" className="text-sm text-destructive">{grant.error.message}</p>}<DialogFooter><Button type="button" variant="outline" disabled={grant.isPending} onClick={onClose}>Cancel</Button><Button type="submit" disabled={!valid || grant.isPending}>{grant.isPending ? 'Granting…' : 'Grant access'}</Button></DialogFooter></form></DialogContent></Dialog>
}

function RevokePlatformAccessDialog({ grant: target, onClose }: { grant: PlatformGrant; onClose: () => void }) {
  const queryClient = useQueryClient()
  const revoke = useMutation({ mutationFn: () => deletePlatformGrant(target), onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: ['platform', 'grants'] }); onClose() } })
  return <Dialog open onOpenChange={(open) => { if (!open && !revoke.isPending) onClose() }}><DialogContent><DialogHeader><DialogTitle>Revoke platform access</DialogTitle><DialogDescription>Revoke platform-administrator access for {target.displayName ?? target.subject}? Their next platform request will be denied.</DialogDescription></DialogHeader>{revoke.isError && <p role="alert" className="text-sm text-destructive">{revoke.error.message}</p>}<DialogFooter><Button type="button" variant="outline" disabled={revoke.isPending} onClick={onClose}>Cancel</Button><Button type="button" variant="destructive" disabled={revoke.isPending} onClick={() => revoke.mutate()}>{revoke.isPending ? 'Revoking…' : 'Revoke access'}</Button></DialogFooter></DialogContent></Dialog>
}

export { PlatformAdministrationPage }
