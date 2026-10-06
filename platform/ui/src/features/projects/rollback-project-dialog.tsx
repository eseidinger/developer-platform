import * as React from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { rollbackProject, type OperationAccepted } from '@/features/projects/projects-api'

function RollbackProjectDialog({ name, targetRevision, currentRevision, onAccepted }: { name: string; targetRevision: number; currentRevision: number; onAccepted: (operation: OperationAccepted) => void }) {
  const [open, setOpen] = React.useState(false)
  const queryClient = useQueryClient()
  const rollback = useMutation({
    mutationFn: () => rollbackProject(name, targetRevision, currentRevision),
    onSuccess: async (operation) => {
      await queryClient.invalidateQueries({ queryKey: ['projects', name, 'revisions'] })
      onAccepted(operation)
      setOpen(false)
    },
  })

  function handleOpenChange(nextOpen: boolean) {
    if (rollback.isPending) return
    setOpen(nextOpen)
    if (!nextOpen) rollback.reset()
  }

  return (
    <>
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}>Roll back</Button>
      <Dialog open={open} onOpenChange={handleOpenChange}>
        <DialogContent showCloseButton={!rollback.isPending}>
          <DialogHeader>
            <DialogTitle>Roll back to revision {targetRevision}</DialogTitle>
            <DialogDescription>This re-applies revision {targetRevision} as a new revision. Databases and current secret values are not rolled back.</DialogDescription>
          </DialogHeader>
          {rollback.isError && <p role="alert" className="text-sm text-destructive">{rollback.error.message}</p>}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => handleOpenChange(false)} disabled={rollback.isPending}>Cancel</Button>
            <Button type="button" onClick={() => rollback.mutate()} disabled={rollback.isPending}>{rollback.isPending ? 'Queueing…' : 'Roll back'}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}

export { RollbackProjectDialog }
