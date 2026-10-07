import * as React from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { ApiError } from '@/api/errors'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { deleteProjectGrant, getProjectGrants, putProjectGrant, type ProjectGrant } from '@/features/projects/projects-api'

const roles = ['viewer', 'developer', 'project-admin'] as const
type GrantDraft = Omit<ProjectGrant, 'grantedAt'>

function ProjectGrants({ name, enabled }: { name: string; enabled: boolean }) {
  const grants = useQuery({ queryKey: ['projects', name, 'grants'], queryFn: () => getProjectGrants(name), enabled })
  const [editing, setEditing] = React.useState<GrantDraft | null>(null)
  const [revoking, setRevoking] = React.useState<ProjectGrant | null>(null)

  if (!enabled || (grants.isError && grants.error instanceof ApiError && grants.error.status === 403)) return null
  if (grants.isLoading) return <section aria-label="Project access" className="rounded-xl border border-border bg-card p-6 text-sm text-muted-foreground">Loading project access…</section>
  if (grants.isError) return <section aria-label="Project access" className="rounded-xl border border-border bg-card p-6"><h2 className="text-lg font-medium">Project access</h2><p role="alert" className="mt-2 text-sm text-destructive">{grants.error.message}</p></section>
  if (!grants.data) return null

  return <section aria-labelledby="access-title" className="rounded-xl border border-border bg-card p-6">
    <div className="flex flex-wrap items-center justify-between gap-3"><div><h2 id="access-title" className="text-lg font-medium">Project access</h2><p className="mt-1 text-sm text-muted-foreground">Roles are enforced by the API on every request. Revoking access takes effect on the recipient’s next request.</p></div><Button variant="outline" onClick={() => setEditing({ issuer: '', subject: '', displayName: null, role: 'viewer' })}>Grant access</Button></div>
    {grants.data.grants.length ? <ul className="mt-4 divide-y divide-border rounded-lg border border-border text-sm">{grants.data.grants.map((grant) => <li key={`${grant.issuer}|${grant.subject}`} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3"><div><p className="font-medium">{grant.displayName ?? grant.subject}</p><p className="text-xs text-muted-foreground break-all">{grant.issuer} · {grant.subject}</p><p className="mt-1 text-xs text-muted-foreground">Granted {new Date(grant.grantedAt).toLocaleString()}</p></div><div className="flex items-center gap-2"><span className="rounded-full bg-muted px-2 py-1 text-xs font-medium">{grant.role}</span><Button size="sm" variant="outline" onClick={() => setEditing({ issuer: grant.issuer, subject: grant.subject, displayName: grant.displayName, role: grant.role })}>Change role</Button><Button size="sm" variant="destructive" onClick={() => setRevoking(grant)}>Revoke</Button></div></li>)}</ul> : <p className="mt-3 text-sm text-muted-foreground">No project grants are recorded.</p>}
    {editing && <GrantDialog name={name} initial={editing} onClose={() => setEditing(null)} />}
    {revoking && <RevokeGrantDialog name={name} grant={revoking} onClose={() => setRevoking(null)} />}
  </section>
}

function GrantDialog({ name, initial, onClose }: { name: string; initial: GrantDraft; onClose: () => void }) {
  const [draft, setDraft] = React.useState(initial)
  const queryClient = useQueryClient()
  const save = useMutation({ mutationFn: () => putProjectGrant(name, draft), onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: ['projects', name, 'grants'] }); onClose() } })
  const isExisting = Boolean(initial.issuer)
  const valid = Boolean(draft.issuer.trim() && draft.subject.trim())
  return <Dialog open onOpenChange={(open) => { if (!open && !save.isPending) onClose() }}><DialogContent><DialogHeader><DialogTitle>{isExisting ? 'Change project role' : 'Grant project access'}</DialogTitle><DialogDescription>{isExisting ? 'Changing a role replaces the existing project grant.' : 'Enter the recipient identity from the configured identity provider.'}</DialogDescription></DialogHeader><form className="space-y-4" onSubmit={(event) => { event.preventDefault(); if (valid) save.mutate() }}><div className="space-y-2"><Label htmlFor="grant-issuer">Issuer</Label><Input id="grant-issuer" autoComplete="off" value={draft.issuer} disabled={isExisting || save.isPending} onChange={(event) => setDraft({ ...draft, issuer: event.target.value })} /></div><div className="space-y-2"><Label htmlFor="grant-subject">Subject ID</Label><Input id="grant-subject" autoComplete="off" value={draft.subject} disabled={isExisting || save.isPending} onChange={(event) => setDraft({ ...draft, subject: event.target.value })} /></div><div className="space-y-2"><Label htmlFor="grant-display-name">Display name (optional)</Label><Input id="grant-display-name" autoComplete="off" value={draft.displayName ?? ''} disabled={save.isPending} onChange={(event) => setDraft({ ...draft, displayName: event.target.value || null })} /></div><div className="space-y-2"><Label htmlFor="grant-role">Role</Label><select id="grant-role" className="h-8 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm" value={draft.role} disabled={save.isPending} onChange={(event) => setDraft({ ...draft, role: event.target.value as ProjectGrant['role'] })}>{roles.map((role) => <option key={role} value={role}>{role}</option>)}</select></div>{save.isError && <p role="alert" className="text-sm text-destructive">{save.error.message}</p>}<DialogFooter><Button type="button" variant="outline" disabled={save.isPending} onClick={onClose}>Cancel</Button><Button type="submit" disabled={!valid || save.isPending}>{save.isPending ? 'Saving…' : isExisting ? 'Change role' : 'Grant access'}</Button></DialogFooter></form></DialogContent></Dialog>
}

function RevokeGrantDialog({ name, grant, onClose }: { name: string; grant: ProjectGrant; onClose: () => void }) {
  const queryClient = useQueryClient()
  const revoke = useMutation({ mutationFn: () => deleteProjectGrant(name, grant), onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: ['projects', name, 'grants'] }); onClose() } })
  return <Dialog open onOpenChange={(open) => { if (!open && !revoke.isPending) onClose() }}><DialogContent><DialogHeader><DialogTitle>Revoke project access</DialogTitle><DialogDescription>Revoke {grant.displayName ?? grant.subject} from {name}? Their next platform request will be denied.</DialogDescription></DialogHeader>{revoke.isError && <p role="alert" className="text-sm text-destructive">{revoke.error.message}</p>}<DialogFooter><Button type="button" variant="outline" disabled={revoke.isPending} onClick={onClose}>Cancel</Button><Button type="button" variant="destructive" disabled={revoke.isPending} onClick={() => revoke.mutate()}>{revoke.isPending ? 'Revoking…' : 'Revoke access'}</Button></DialogFooter></DialogContent></Dialog>
}

export { ProjectGrants }
