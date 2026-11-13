import * as React from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { ApiError } from '@/api/errors'
import { useAuth } from '@/auth/auth-context'
import { Badge, Button } from '@mantine/core'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@mantine/core'
import { InputLabel as Label } from '@mantine/core'
import styles from './platform-administration-page.module.css'
import {
  deletePlatformGrant,
  getPlatformGrants,
  putPlatformGrant,
  type PlatformGrant,
} from '@/features/projects/projects-api'

type PlatformGrantDraft = Omit<PlatformGrant, 'grantedAt' | 'role'>

function PlatformAdministrationPage() {
  const { status, user } = useAuth()
  const grants = useQuery({
    queryKey: ['platform', 'grants'],
    queryFn: getPlatformGrants,
    enabled: status === 'authenticated',
  })
  const [granting, setGranting] = React.useState(false)
  const [revoking, setRevoking] = React.useState<PlatformGrant | null>(null)
  const issuer = typeof user?.profile.iss === 'string' ? user.profile.iss : null
  const subject =
    typeof user?.profile.sub === 'string' ? user.profile.sub : null

  if (status !== 'authenticated')
    return (
      <section>
        <h1 className={styles.pageTitle}>Platform administration</h1>
        <p className={styles.subtext}>
          Sign in to inspect platform administration access.
        </p>
      </section>
    )
  if (grants.isLoading)
    return (
      <section>
        <h1 className={styles.pageTitle}>Platform administration</h1>
        <p role="status" className={styles.subtext}>
          Loading platform grants…
        </p>
      </section>
    )
  if (
    grants.isError &&
    grants.error instanceof ApiError &&
    grants.error.status === 403
  )
    return (
      <section>
        <h1 className={styles.pageTitle}>Platform administration</h1>
        <p className={styles.subtext}>
          Your current platform access does not allow administration changes.
        </p>
      </section>
    )
  if (grants.isError)
    return (
      <section>
        <h1 className={styles.pageTitle}>Platform administration</h1>
        <p role="alert" className={styles.errorLarge}>
          {grants.error.message}
        </p>
      </section>
    )

  return (
    <section aria-labelledby="platform-admin-title" className={styles.page}>
      <div className={styles.stackSmall}>
        <h1 id="platform-admin-title" className={styles.pageTitle}>
          Platform administration
        </h1>
        <p className={styles.muted}>
          Platform administrators can create or revoke platform-administrator
          access. The API enforces every action; this screen does not grant
          authority itself.
        </p>
      </div>
      <section aria-labelledby="platform-grants-title" className={styles.panel}>
        <div className={styles.header}>
          <div>
            <h2 id="platform-grants-title" className={styles.sectionTitle}>
              Platform administrators
            </h2>
            <p className={styles.intro}>
              Grant only to trusted operators. You cannot revoke your own
              platform access here or through the API.
            </p>
          </div>
          <Button onClick={() => setGranting(true)}>
            Grant platform access
          </Button>
        </div>
        {grants.data?.length ? (
          <ul className={styles.grantList}>
            {grants.data.map((grant) => {
              const isSelf =
                grant.issuer === issuer && grant.subject === subject
              return (
                <li
                  key={`${grant.issuer}|${grant.subject}`}
                  className={styles.grantRow}
                >
                  <div>
                    <p className={styles.strong}>
                      {grant.displayName ?? grant.subject}
                      {isSelf ? ' (you)' : ''}
                    </p>
                    <p className={styles.identifier}>
                      {grant.issuer} · {grant.subject}
                    </p>
                    <p className={styles.metadata}>
                      Granted {new Date(grant.grantedAt).toLocaleString()}
                    </p>
                  </div>
                  {isSelf ? (
                    <Badge variant="light" color="indigo">
                      Your access
                    </Badge>
                  ) : (
                    <Button
                      size="sm"
                      color="red"
                      variant="outline"
                      onClick={() => setRevoking(grant)}
                    >
                      Revoke
                    </Button>
                  )}
                </li>
              )
            })}
          </ul>
        ) : (
          <p className={styles.empty}>No platform grants are recorded.</p>
        )}
      </section>
      {granting && (
        <GrantPlatformAccessDialog onClose={() => setGranting(false)} />
      )}
      {revoking && (
        <RevokePlatformAccessDialog
          grant={revoking}
          onClose={() => setRevoking(null)}
        />
      )}
    </section>
  )
}

function GrantPlatformAccessDialog({ onClose }: { onClose: () => void }) {
  const [draft, setDraft] = React.useState<PlatformGrantDraft>({
    issuer: '',
    subject: '',
    displayName: null,
  })
  const queryClient = useQueryClient()
  const grant = useMutation({
    mutationFn: () => putPlatformGrant(draft),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['platform', 'grants'] })
      onClose()
    },
  })
  const valid = Boolean(draft.issuer.trim() && draft.subject.trim())
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !grant.isPending) onClose()
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Grant platform access</DialogTitle>
          <DialogDescription>
            Enter the recipient identity from the configured identity provider.
            This gives platform-administrator access across all projects.
          </DialogDescription>
        </DialogHeader>
        <form
          className={styles.stackLarge}
          onSubmit={(event) => {
            event.preventDefault()
            if (valid) grant.mutate()
          }}
        >
          <div className={styles.stackSmall}>
            <Label htmlFor="platform-grant-issuer">Issuer</Label>
            <Input
              id="platform-grant-issuer"
              autoComplete="off"
              value={draft.issuer}
              disabled={grant.isPending}
              onChange={(event) =>
                setDraft({ ...draft, issuer: event.target.value })
              }
            />
          </div>
          <div className={styles.stackSmall}>
            <Label htmlFor="platform-grant-subject">Subject ID</Label>
            <Input
              id="platform-grant-subject"
              autoComplete="off"
              value={draft.subject}
              disabled={grant.isPending}
              onChange={(event) =>
                setDraft({ ...draft, subject: event.target.value })
              }
            />
          </div>
          <div className={styles.stackSmall}>
            <Label htmlFor="platform-grant-display-name">
              Display name (optional)
            </Label>
            <Input
              id="platform-grant-display-name"
              autoComplete="off"
              value={draft.displayName ?? ''}
              disabled={grant.isPending}
              onChange={(event) =>
                setDraft({ ...draft, displayName: event.target.value || null })
              }
            />
          </div>
          {grant.isError && (
            <p role="alert" className={styles.error}>
              {grant.error.message}
            </p>
          )}
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              disabled={grant.isPending}
              onClick={onClose}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={!valid || grant.isPending}>
              {grant.isPending ? 'Granting…' : 'Grant access'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function RevokePlatformAccessDialog({
  grant: target,
  onClose,
}: {
  grant: PlatformGrant
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const revoke = useMutation({
    mutationFn: () => deletePlatformGrant(target),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['platform', 'grants'] })
      onClose()
    },
  })
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !revoke.isPending) onClose()
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Revoke platform access</DialogTitle>
          <DialogDescription>
            Revoke platform-administrator access for{' '}
            {target.displayName ?? target.subject}? Their next platform request
            will be denied.
          </DialogDescription>
        </DialogHeader>
        {revoke.isError && (
          <p role="alert" className={styles.error}>
            {revoke.error.message}
          </p>
        )}
        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            disabled={revoke.isPending}
            onClick={onClose}
          >
            Cancel
          </Button>
          <Button
            type="button"
            color="red"
            disabled={revoke.isPending}
            onClick={() => revoke.mutate()}
          >
            {revoke.isPending ? 'Revoking…' : 'Revoke access'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export { PlatformAdministrationPage }
