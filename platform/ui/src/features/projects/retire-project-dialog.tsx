import * as React from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { getRetirementPreview, retireProject } from '@/features/projects/projects-api'

function RetireProjectDialog({ name }: { name: string }) {
  const [open, setOpen] = React.useState(false)
  const [confirmation, setConfirmation] = React.useState('')
  const [retirementStatus, setRetirementStatus] = React.useState<string | null>(null)
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const preview = useQuery({ queryKey: ['projects', name, 'retirement-preview'], queryFn: () => getRetirementPreview(name), enabled: open })
  const retire = useMutation({
    mutationFn: () => retireProject(name, preview.data?.scopeToken ?? ''),
    onSuccess: async (result) => {
      if (result.status === 'retired') {
        await queryClient.invalidateQueries({ queryKey: ['projects'] })
        void navigate('/')
      } else {
        setRetirementStatus(result.status)
      }
    },
  })

  function handleOpenChange(nextOpen: boolean) {
    if (retire.isPending) return
    setOpen(nextOpen)
    if (!nextOpen) { setConfirmation(''); setRetirementStatus(null); retire.reset() }
  }

  const canRetire = Boolean(preview.data && preview.data.blockers.length === 0 && confirmation === name)
  return (
    <>
      <Button variant="destructive" onClick={() => setOpen(true)}>Retire project</Button>
      <Dialog open={open} onOpenChange={handleOpenChange}>
        <DialogContent className="sm:max-w-xl" showCloseButton={!retire.isPending}>
          <DialogHeader><DialogTitle>Retire {name}</DialogTitle><DialogDescription>This removes the project namespace and revokes project access. The database, database role, catalog, and revisions are retained.</DialogDescription></DialogHeader>
          {preview.isLoading && <p role="status" className="text-sm text-muted-foreground">Loading retirement scope…</p>}
          {preview.isError && <p role="alert" className="text-sm text-destructive">{preview.error.message}</p>}
          {preview.data && <><div className="space-y-2 text-sm"><p className="font-medium">Will remove</p><ul className="max-h-32 list-disc overflow-auto pl-5 text-muted-foreground">{preview.data.removes.map((resource) => <li key={`${resource.kind}-${resource.name}`}>{resource.kind} {resource.name}</li>)}</ul><p className="font-medium">Will retain</p><ul className="list-disc pl-5 text-muted-foreground">{Object.entries(preview.data.retains).map(([key, value]) => <li key={key}>{key}: {String(value)}</li>)}</ul></div>{preview.data.blockers.length > 0 ? <p role="alert" className="text-sm text-destructive">Retirement is blocked: {preview.data.blockers.join(', ')}.</p> : <div className="space-y-2"><label htmlFor="retirement-confirmation" className="text-sm font-medium">Type {name} to confirm</label><Input id="retirement-confirmation" autoComplete="off" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} disabled={retire.isPending} /></div>}</>}
          {retirementStatus === 'retiring' && <p role="status" className="text-sm text-muted-foreground">Namespace deletion is still in progress. Repeat the confirmed request to complete retirement.</p>}
          {retire.isError && <p role="alert" className="text-sm text-destructive">{retire.error.message}</p>}
          <DialogFooter><Button type="button" variant="outline" onClick={() => handleOpenChange(false)} disabled={retire.isPending}>Cancel</Button><Button type="button" variant="destructive" onClick={() => retire.mutate()} disabled={!canRetire || retire.isPending}>{retire.isPending ? 'Retiring…' : retirementStatus === 'retiring' ? 'Complete retirement' : 'Retire project'}</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}

export { RetireProjectDialog }
