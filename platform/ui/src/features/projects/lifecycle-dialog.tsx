import * as React from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Button, Input } from '@mantine/core'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  getLifecyclePreview,
  startLifecycle,
  type LifecycleAction,
} from './lifecycle-api'
import styles from './project-dialogs.module.css'

const labels = {
  retire: 'Retire project',
  restore: 'Restore project',
  purge: 'Permanently purge',
}
const descriptions = {
  retire:
    'Stop the application and revoke access. Store data, history and an encrypted recovery point are retained.',
  restore:
    'Rebuild the application from its recovery point using retained data. Required credentials are issued again; revoked credentials remain invalid.',
  purge:
    'Permanently remove this project, its stores, history, audit records, telemetry and backups. Shared recovery snapshots containing this project will also be removed after a clean backup is verified. This cannot be undone.',
}

export function LifecycleDialog({
  name,
  action,
  onAccepted,
}: {
  name: string
  action: LifecycleAction
  onAccepted: (operationId: string) => void
}) {
  const [open, setOpen] = React.useState(false)
  const [confirmation, setConfirmation] = React.useState('')
  const preview = useQuery({
    queryKey: ['projects', name, action, 'preview'],
    queryFn: () => getLifecyclePreview(name, action),
    enabled: open,
    staleTime: 0,
  })
  const mutation = useMutation({
    mutationFn: () => {
      if (!preview.data) throw new Error('Load a current preview first.')
      return startLifecycle(preview.data)
    },
    onSuccess: (operation) => {
      onAccepted(operation.operation_id)
      setOpen(false)
      setConfirmation('')
    },
    onError: async () => {
      setConfirmation('')
      await preview.refetch()
    },
  })
  const id = action + '-confirmation'
  return (
    <>
      <Button
        color={action === 'restore' ? undefined : 'red'}
        variant="outline"
        onClick={() => {
          mutation.reset()
          setOpen(true)
        }}
      >
        {labels[action]}
      </Button>
      <Dialog
        open={open}
        onOpenChange={(value) => {
          if (!mutation.isPending) {
            setOpen(value)
            setConfirmation('')
          }
        }}
      >
        <DialogContent className={styles.wideModal}>
          <DialogHeader>
            <DialogTitle>
              {labels[action]}: {name}
            </DialogTitle>
            <DialogDescription>{descriptions[action]}</DialogDescription>
          </DialogHeader>
          {preview.isPending && <p role="status">Loading project scope…</p>}
          {preview.isError && <p role="alert">{preview.error.message}</p>}
          {preview.data && (
            <>
              <p>Project ID: {preview.data.project_id}</p>
              {preview.data.blockers.length > 0 && (
                <p role="alert">Blocked: {preview.data.blockers.join(', ')}</p>
              )}
              <label htmlFor={id}>Type {name} to confirm</label>
              <Input
                id={id}
                value={confirmation}
                autoComplete="off"
                onChange={(event) => setConfirmation(event.target.value)}
                disabled={mutation.isPending}
              />
            </>
          )}
          {mutation.isError && <p role="alert">{mutation.error.message}</p>}
          <DialogFooter>
            <Button
              variant="outline"
              disabled={mutation.isPending}
              onClick={() => setOpen(false)}
            >
              Cancel
            </Button>
            <Button
              color={action === 'restore' ? undefined : 'red'}
              disabled={
                !preview.data ||
                preview.data.blockers.length > 0 ||
                confirmation !== name ||
                mutation.isPending
              }
              onClick={() => mutation.mutate()}
            >
              {mutation.isPending ? 'Submitting…' : labels[action]}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
