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
import {
  getRetirementPreview,
  retireProject,
} from '@/features/projects/projects-api'

function RetireProjectDialog({ name }: { name: string }) {
  const [open, setOpen] = React.useState(false)
  const [confirmation, setConfirmation] = React.useState('')
  const [retirementStatus, setRetirementStatus] = React.useState<string | null>(
    null,
  )
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const preview = useQuery({
    queryKey: ['projects', name, 'retirement-preview'],
    queryFn: () => getRetirementPreview(name),
    enabled: open,
  })
  const retire = useMutation({
    mutationFn: () => retireProject(name, preview.data?.scopeToken ?? ''),
    onSuccess: async (result) => {
      if (result.status === 'retired') {
        await queryClient.invalidateQueries({ queryKey: ['projects'] })
        void navigate('/')
      } else {
        setRetirementStatus(result.status)
        await preview.refetch()
      }
    },
    onError: async () => {
      setConfirmation('')
      await preview.refetch()
    },
  })

  function handleOpenChange(nextOpen: boolean) {
    if (retire.isPending) return
    setOpen(nextOpen)
    if (!nextOpen) {
      setConfirmation('')
      setRetirementStatus(null)
      retire.reset()
    }
  }

  const canRetire = Boolean(
    preview.data && preview.data.blockers.length === 0 && confirmation === name,
  )
  return (
    <>
      <Button color="red" variant="outline" onClick={() => setOpen(true)}>
        Retire project
      </Button>
      <Dialog open={open} onOpenChange={handleOpenChange}>
        <DialogContent
          className={styles.wideModal}
          showCloseButton={!retire.isPending}
        >
          <DialogHeader>
            <DialogTitle>Retire {name}</DialogTitle>
            <DialogDescription>
              This removes the project namespace and revokes project access.
              Named stores are retired and their grants are revoked, including
              access from other projects. Store data, catalog, and revisions are
              retained.
            </DialogDescription>
          </DialogHeader>
          {preview.isLoading && (
            <p role="status" className={styles.mutedSmall}>
              Loading retirement scope…
            </p>
          )}
          {preview.isError && (
            <p role="alert" className={styles.error}>
              {preview.error.message}
            </p>
          )}
          {preview.data && (
            <>
              <div className={styles.smallStack}>
                <p className={styles.strong}>Will remove</p>
                <ul className={styles.boundedList}>
                  {preview.data.removes.map((resource) => (
                    <li key={`${resource.kind}-${resource.name}`}>
                      {resource.kind} {resource.name}
                    </li>
                  ))}
                </ul>
                <p className={styles.strong}>Will retain</p>
                <ul className={styles.mutedBulletList}>
                  {Object.entries(preview.data.retains).map(([key, value]) => (
                    <li key={key}>
                      {key}: {String(value)}
                    </li>
                  ))}
                </ul>
              </div>
              {preview.data.stores.length > 0 && (
                <div className={styles.small}>
                  <p className={styles.strong}>
                    Stores to retire (data retained)
                  </p>
                  <ul className={styles.bulletList}>
                    {preview.data.stores.map((store) => (
                      <li key={store.id}>
                        {store.name} ({store.id})
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <p className={styles.small}>
                Named store grants to revoke: {preview.data.storeGrantCount}
              </p>
              {preview.data.blockers.length > 0 ? (
                <p role="alert" className={styles.error}>
                  Retirement is blocked: {preview.data.blockers.join(', ')}.
                </p>
              ) : (
                <div className={styles.stackSmall}>
                  <label
                    htmlFor="retirement-confirmation"
                    className={styles.smallStrong}
                  >
                    Type {name} to confirm
                  </label>
                  <Input
                    id="retirement-confirmation"
                    autoComplete="off"
                    value={confirmation}
                    onChange={(event) => setConfirmation(event.target.value)}
                    disabled={retire.isPending}
                  />
                </div>
              )}
            </>
          )}
          {retirementStatus === 'retiring' && (
            <p role="status" className={styles.mutedSmall}>
              Namespace deletion is still in progress. Repeat the confirmed
              request to complete retirement.
            </p>
          )}
          {retire.isError && (
            <p role="alert" className={styles.error}>
              {retire.error.message}
            </p>
          )}
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => handleOpenChange(false)}
              disabled={retire.isPending}
            >
              Cancel
            </Button>
            <Button
              type="button"
              color="red"
              onClick={() => retire.mutate()}
              disabled={!canRetire || retire.isPending}
            >
              {retire.isPending
                ? 'Retiring…'
                : retirementStatus === 'retiring'
                  ? 'Complete retirement'
                  : 'Retire project'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}

export { RetireProjectDialog }
