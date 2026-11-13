import styles from './project-dialogs.module.css'
import * as React from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'

import { Button } from '@mantine/core'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@mantine/core'
import { getPurgePreview, purgeProject } from '@/features/projects/projects-api'

function PurgeProjectDialog({ name }: { name: string }) {
  const [open, setOpen] = React.useState(false)
  const [confirmation, setConfirmation] = React.useState('')
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const preview = useQuery({
    queryKey: ['operator', 'projects', name, 'purge-preview'],
    queryFn: () => getPurgePreview(name),
    enabled: open,
  })
  const purge = useMutation({
    mutationFn: () => purgeProject(name, preview.data?.scopeToken ?? ''),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['projects'] })
      queryClient.removeQueries({ queryKey: ['projects', name] })
      void navigate('/')
    },
  })
  const pendingCredentials = Object.entries(
    preview.data?.credentialCleanup ?? {},
  ).filter(([status, count]) => status !== 'revoked' && count > 0)
  const canPurge = Boolean(
    preview.data && confirmation === name && pendingCredentials.length === 0,
  )

  function handleOpenChange(nextOpen: boolean) {
    if (purge.isPending) return
    setOpen(nextOpen)
    if (!nextOpen) {
      setConfirmation('')
      purge.reset()
    }
  }

  return (
    <>
      <Button color="red" variant="outline" onClick={() => setOpen(true)}>
        Permanently purge
      </Button>
      <Dialog open={open} onOpenChange={handleOpenChange}>
        <DialogContent
          className={styles.wideModal}
          showCloseButton={!purge.isPending}
        >
          <DialogHeader>
            <DialogTitle>Permanently purge {name}</DialogTitle>
            <DialogDescription>
              This cannot be undone. It removes the retained PostgreSQL
              database, database role, catalog, revision history, operations,
              credentials, and retirement inventory. Append-only audit records
              are retained.
            </DialogDescription>
          </DialogHeader>
          {preview.isLoading && (
            <p role="status" className={styles.mutedSmall}>
              Loading permanent-deletion scope…
            </p>
          )}
          {preview.isError && (
            <p role="alert" className={styles.error}>
              {preview.error.message}
            </p>
          )}
          {preview.data && (
            <div className={styles.smallMediumStack}>
              <div>
                <p className={styles.strong}>Will permanently remove</p>
                <ul className={styles.indentedList}>
                  <li>Database: {preview.data.database}</li>
                  <li>Database role: {preview.data.role}</li>
                  {preview.data.catalog.map((item) => (
                    <li key={item}>Catalog: {item}</li>
                  ))}
                </ul>
              </div>
              <p className={styles.muted}>
                Audit records retained:{' '}
                {preview.data.auditRecordsRetained ? 'yes' : 'no'}.
              </p>
              {pendingCredentials.length > 0 ? (
                <p role="alert" className={styles.danger}>
                  Purge is blocked until credential cleanup completes:{' '}
                  {pendingCredentials
                    .map(([status, count]) => `${count} ${status}`)
                    .join(', ')}
                  .
                </p>
              ) : (
                <div className={styles.stackSmall}>
                  <label htmlFor="purge-confirmation" className={styles.strong}>
                    Type {name} to permanently purge it
                  </label>
                  <Input
                    id="purge-confirmation"
                    autoComplete="off"
                    value={confirmation}
                    onChange={(event) => setConfirmation(event.target.value)}
                    disabled={purge.isPending}
                  />
                </div>
              )}
            </div>
          )}
          {purge.isError && (
            <p role="alert" className={styles.error}>
              {purge.error.message}
            </p>
          )}
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => handleOpenChange(false)}
              disabled={purge.isPending}
            >
              Cancel
            </Button>
            <Button
              type="button"
              color="red"
              onClick={() => purge.mutate()}
              disabled={!canPurge || purge.isPending}
            >
              {purge.isPending ? 'Purging…' : 'Permanently purge'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}

export { PurgeProjectDialog }
