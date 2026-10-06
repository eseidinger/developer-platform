import * as React from 'react'
import { useQueryClient } from '@tanstack/react-query'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { confirmProjectSecretRotation, revertProjectSecretRotation } from '@/features/projects/projects-api'

type Action = 'confirm' | 'revert'

function SecretRotationActions({ name, secret, activationState }: { name: string; secret: string; activationState: string }) {
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
      else await revertProjectSecretRotation(name, secret)
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

  return (
    <>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="outline" onClick={() => setAction('revert')}>Revert rotation</Button>
        <Button size="sm" variant="outline" onClick={() => setAction('confirm')} disabled={!canConfirm}>Confirm rotation</Button>
      </div>
      {!canConfirm && <p className="text-xs text-muted-foreground">Confirmation is available after activation is active.</p>}
      <Dialog open={action !== null} onOpenChange={(open) => { if (!open) close() }}>
        <DialogContent showCloseButton={!isSubmitting}>
          <DialogHeader>
            <DialogTitle>{isConfirm ? 'Confirm secret rotation' : 'Revert secret rotation'}</DialogTitle>
            <DialogDescription>{isConfirm ? `This permanently discards the previous value for ${secret}.` : `This restores the previous value for ${secret} and restarts the workload.`}</DialogDescription>
          </DialogHeader>
          {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={close} disabled={isSubmitting}>Cancel</Button>
            <Button type="button" onClick={() => void submit()} disabled={isSubmitting}>{isSubmitting ? 'Applying…' : isConfirm ? 'Confirm rotation' : 'Revert rotation'}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}

export { SecretRotationActions }
