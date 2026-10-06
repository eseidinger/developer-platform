import * as React from 'react'
import { useQueryClient } from '@tanstack/react-query'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { confirmProjectSecretRotation, deleteProjectSecret, revertProjectSecretRotation } from '@/features/projects/projects-api'

type Action = 'confirm' | 'revert' | 'delete'

function SecretActions({ name, secret, state, activationState }: { name: string; secret: string; state: string; activationState: string }) {
  const [action, setAction] = React.useState<Action | null>(null)
  const [error, setError] = React.useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = React.useState(false)
  const queryClient = useQueryClient()

  function close() {
    if (isSubmitting) return
    setAction(null)
    setError(null)
  }

  async function submit() {
    if (!action) return
    setIsSubmitting(true)
    setError(null)
    try {
      if (action === 'confirm') await confirmProjectSecretRotation(name, secret)
      else if (action === 'revert') await revertProjectSecretRotation(name, secret)
      else await deleteProjectSecret(name, secret)
      await queryClient.invalidateQueries({ queryKey: ['projects', name, 'secrets'] })
      setAction(null)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to update secret rotation.')
    } finally {
      setIsSubmitting(false)
    }
  }

  const canConfirm = activationState === 'active'
  const isConfirm = action === 'confirm'
  const isRevert = action === 'revert'
  const isDelete = action === 'delete'

  return (
    <>
      <div className="flex flex-wrap gap-2">
        {state === 'rotating' && <Button size="sm" variant="outline" onClick={() => setAction('revert')}>Revert rotation</Button>}
        {state === 'rotating' && <Button size="sm" variant="outline" onClick={() => setAction('confirm')} disabled={!canConfirm}>Confirm rotation</Button>}
        <Button size="sm" variant="destructive" onClick={() => setAction('delete')}>Delete</Button>
      </div>
      {state === 'rotating' && !canConfirm && <p className="text-xs text-muted-foreground">Confirmation is available after activation is active.</p>}
      <Dialog open={action !== null} onOpenChange={(open) => { if (!open) close() }}>
        <DialogContent showCloseButton={!isSubmitting}>
          <DialogHeader>
            <DialogTitle>{isConfirm ? 'Confirm secret rotation' : isRevert ? 'Revert secret rotation' : 'Delete project secret'}</DialogTitle>
            <DialogDescription>{isConfirm ? `This permanently discards the previous value for ${secret}.` : isRevert ? `This restores the previous value for ${secret} and restarts the workload.` : `This permanently removes ${secret} and restarts the workload.`}</DialogDescription>
          </DialogHeader>
          {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={close} disabled={isSubmitting}>Cancel</Button>
            <Button type="button" variant={isDelete ? 'destructive' : 'default'} onClick={() => void submit()} disabled={isSubmitting}>{isSubmitting ? 'Applying…' : isConfirm ? 'Confirm rotation' : isRevert ? 'Revert rotation' : 'Delete secret'}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}

export { SecretActions }
