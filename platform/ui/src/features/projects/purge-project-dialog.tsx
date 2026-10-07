import * as React from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { getPurgePreview, purgeProject } from '@/features/projects/projects-api'

function PurgeProjectDialog({ name }: { name: string }) {
  const [open, setOpen] = React.useState(false)
  const [confirmation, setConfirmation] = React.useState('')
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const preview = useQuery({ queryKey: ['operator', 'projects', name, 'purge-preview'], queryFn: () => getPurgePreview(name), enabled: open })
  const purge = useMutation({
    mutationFn: () => purgeProject(name, preview.data?.scopeToken ?? ''),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['projects'] })
      queryClient.removeQueries({ queryKey: ['projects', name] })
      void navigate('/')
    },
  })
  const pendingCredentials = Object.entries(preview.data?.credentialCleanup ?? {}).filter(([status, count]) => status !== 'revoked' && count > 0)
  const canPurge = Boolean(preview.data && confirmation === name && pendingCredentials.length === 0)

  function handleOpenChange(nextOpen: boolean) {
    if (purge.isPending) return
    setOpen(nextOpen)
    if (!nextOpen) { setConfirmation(''); purge.reset() }
  }

  return <><Button variant="destructive" onClick={() => setOpen(true)}>Permanently purge</Button><Dialog open={open} onOpenChange={handleOpenChange}><DialogContent className="sm:max-w-xl" showCloseButton={!purge.isPending}><DialogHeader><DialogTitle>Permanently purge {name}</DialogTitle><DialogDescription>This cannot be undone. It removes the retained PostgreSQL database, database role, catalog, revision history, operations, credentials, and retirement inventory. Append-only audit records are retained.</DialogDescription></DialogHeader>{preview.isLoading && <p role="status" className="text-sm text-muted-foreground">Loading permanent-deletion scope…</p>}{preview.isError && <p role="alert" className="text-sm text-destructive">{preview.error.message}</p>}{preview.data && <div className="space-y-3 text-sm"><div><p className="font-medium">Will permanently remove</p><ul className="mt-1 list-disc pl-5 text-muted-foreground"><li>Database: {preview.data.database}</li><li>Database role: {preview.data.role}</li>{preview.data.catalog.map((item) => <li key={item}>Catalog: {item}</li>)}</ul></div><p className="text-muted-foreground">Audit records retained: {preview.data.auditRecordsRetained ? 'yes' : 'no'}.</p>{pendingCredentials.length > 0 ? <p role="alert" className="text-destructive">Purge is blocked until credential cleanup completes: {pendingCredentials.map(([status, count]) => `${count} ${status}`).join(', ')}.</p> : <div className="space-y-2"><label htmlFor="purge-confirmation" className="font-medium">Type {name} to permanently purge it</label><Input id="purge-confirmation" autoComplete="off" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} disabled={purge.isPending} /></div>}</div>}{purge.isError && <p role="alert" className="text-sm text-destructive">{purge.error.message}</p>}<DialogFooter><Button type="button" variant="outline" onClick={() => handleOpenChange(false)} disabled={purge.isPending}>Cancel</Button><Button type="button" variant="destructive" onClick={() => purge.mutate()} disabled={!canPurge || purge.isPending}>{purge.isPending ? 'Purging…' : 'Permanently purge'}</Button></DialogFooter></DialogContent></Dialog></>
}

export { PurgeProjectDialog }
