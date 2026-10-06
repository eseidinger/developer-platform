import * as React from 'react'
import { useMutation } from '@tanstack/react-query'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { restartProject, type OperationAccepted } from '@/features/projects/projects-api'

function RestartProjectDialog({ name, onAccepted }: { name: string; onAccepted: (operation: OperationAccepted) => void }) {
  const [open, setOpen] = React.useState(false)
  const restart = useMutation({
    mutationFn: () => restartProject(name),
    onSuccess: (operation) => {
      onAccepted(operation)
      setOpen(false)
    },
  })

  function handleOpenChange(nextOpen: boolean) {
    if (restart.isPending) return
    setOpen(nextOpen)
    if (!nextOpen) restart.reset()
  }

  return (
    <>
      <Button variant="outline" onClick={() => setOpen(true)}>Restart</Button>
      <Dialog open={open} onOpenChange={handleOpenChange}>
        <DialogContent showCloseButton={!restart.isPending}>
          <DialogHeader>
            <DialogTitle>Restart application</DialogTitle>
            <DialogDescription>This performs a rolling restart of the current revision. The desired application specification and database data are unchanged.</DialogDescription>
          </DialogHeader>
          {restart.isError && <p role="alert" className="text-sm text-destructive">{restart.error.message}</p>}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => handleOpenChange(false)} disabled={restart.isPending}>Cancel</Button>
            <Button type="button" onClick={() => restart.mutate()} disabled={restart.isPending}>{restart.isPending ? 'Queueing…' : 'Restart'}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}

export { RestartProjectDialog }
