import styles from './project-dialogs.module.css'
import * as React from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'

import { Button } from '@mantine/core'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { InputLabel as Label } from '@mantine/core'
import { requestDataServiceRecovery } from '@/features/projects/projects-api'

type Reason = 'unavailable' | 'access' | 'data_integrity' | 'other'

function RequestRecoveryDialog({ name }: { name: string }) {
  const [open, setOpen] = React.useState(false)
  const [reason, setReason] = React.useState<Reason>('unavailable')
  const queryClient = useQueryClient()
  const request = useMutation({
    mutationFn: () => requestDataServiceRecovery(name, reason),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ['projects', name, 'data-services'],
      })
      setOpen(false)
    },
  })

  function handleOpenChange(nextOpen: boolean) {
    if (request.isPending) return
    setOpen(nextOpen)
    if (!nextOpen) request.reset()
  }

  return (
    <>
      <Button variant="outline" onClick={() => setOpen(true)}>
        Request recovery
      </Button>
      <Dialog open={open} onOpenChange={handleOpenChange}>
        <DialogContent showCloseButton={!request.isPending}>
          <DialogHeader>
            <DialogTitle>Request data-service recovery</DialogTitle>
            <DialogDescription>
              This creates a bounded request for operator review. Do not include
              credentials or incident details.
            </DialogDescription>
          </DialogHeader>
          <div className={styles.stackSmall}>
            <Label htmlFor="recovery-reason">Reason category</Label>
            <select
              id="recovery-reason"
              className={styles.field}
              value={reason}
              onChange={(event) => setReason(event.target.value as Reason)}
              disabled={request.isPending}
            >
              <option value="unavailable">Service unavailable</option>
              <option value="access">Access issue</option>
              <option value="data_integrity">Data integrity</option>
              <option value="other">Other</option>
            </select>
          </div>
          {request.isError && (
            <p role="alert" className={styles.error}>
              {request.error.message}
            </p>
          )}
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => handleOpenChange(false)}
              disabled={request.isPending}
            >
              Cancel
            </Button>
            <Button
              type="button"
              onClick={() => request.mutate()}
              disabled={request.isPending}
            >
              {request.isPending ? 'Requesting…' : 'Request recovery'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}

export { RequestRecoveryDialog }
