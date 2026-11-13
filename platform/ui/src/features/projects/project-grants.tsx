import * as React from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { ApiError } from '@/api/errors'
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
import { InputLabel as Label } from '@mantine/core'
import styles from './project-grants.module.css'
import {
  deleteProjectGrant,
  getProjectGrants,
  putProjectGrant,
  type ProjectGrant,
} from '@/features/projects/projects-api'

const roles = ['viewer', 'developer', 'project-admin'] as const
type GrantDraft = Omit<ProjectGrant, 'grantedAt'>

function ProjectGrants({ name, enabled }: { name: string; enabled: boolean }) {
  const grants = useQuery({
    queryKey: ['projects', name, 'grants'],
    queryFn: () => getProjectGrants(name),
    enabled,
  })
  const [editing, setEditing] = React.useState<GrantDraft | null>(null)
  const [revoking, setRevoking] = React.useState<ProjectGrant | null>(null)

  if (
    !enabled ||
    (grants.isError &&
      grants.error instanceof ApiError &&
      grants.error.status === 403)
  )
    return null
  if (grants.isLoading)
    return (
      <section aria-label="Project access" className={styles.emptyPanel}>
        Loading project access…
      </section>
    )
  if (grants.isError)
    return (
      <section aria-label="Project access" className={styles.panel}>
        <h2 className={styles.sectionTitle}>Project access</h2>
        <p role="alert" className={styles.errorBelow}>
          {grants.error.message}
        </p>
      </section>
    )
  if (!grants.data) return null

  return (
    <section aria-labelledby="access-title" className={styles.panel}>
      <div className={styles.header}>
        <div>
          <h2 id="access-title" className={styles.sectionTitle}>
            Project access
          </h2>
          <p className={styles.mutedSmallBelow}>
            Roles are enforced by the API on every request. Revoking access
            takes effect on the recipient’s next request.
          </p>
        </div>
        <Button
          variant="outline"
          onClick={() =>
            setEditing({
              issuer: '',
              subject: '',
              displayName: null,
              role: 'viewer',
            })
          }
        >
          Grant access
        </Button>
      </div>
      {grants.data.grants.length ? (
        <ul className={styles.grantList}>
          {grants.data.grants.map((grant) => (
            <li
              key={`${grant.issuer}|${grant.subject}`}
              className={styles.grantRow}
            >
              <div>
                <p className={styles.strong}>
                  {grant.displayName ?? grant.subject}
                </p>
                <p className={styles.identifier}>
                  {grant.issuer} · {grant.subject}
                </p>
                <p className={styles.mutedTinyBelow}>
                  Granted {new Date(grant.grantedAt).toLocaleString()}
                </p>
              </div>
              <div className={styles.inlineGroup}>
                <span className={styles.roleBadge}>{grant.role}</span>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() =>
                    setEditing({
                      issuer: grant.issuer,
                      subject: grant.subject,
                      displayName: grant.displayName,
                      role: grant.role,
                    })
                  }
                >
                  Change role
                </Button>
                <Button
                  size="sm"
                  color="red"
                  onClick={() => setRevoking(grant)}
                >
                  Revoke
                </Button>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className={styles.empty}>No project grants are recorded.</p>
      )}
      {editing && (
        <GrantDialog
          name={name}
          initial={editing}
          onClose={() => setEditing(null)}
        />
      )}
      {revoking && (
        <RevokeGrantDialog
          name={name}
          grant={revoking}
          onClose={() => setRevoking(null)}
        />
      )}
    </section>
  )
}

function GrantDialog({
  name,
  initial,
  onClose,
}: {
  name: string
  initial: GrantDraft
  onClose: () => void
}) {
  const [draft, setDraft] = React.useState(initial)
  const queryClient = useQueryClient()
  const save = useMutation({
    mutationFn: () => putProjectGrant(name, draft),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ['projects', name, 'grants'],
      })
      onClose()
    },
  })
  const isExisting = Boolean(initial.issuer)
  const valid = Boolean(draft.issuer.trim() && draft.subject.trim())
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !save.isPending) onClose()
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {isExisting ? 'Change project role' : 'Grant project access'}
          </DialogTitle>
          <DialogDescription>
            {isExisting
              ? 'Changing a role replaces the existing project grant.'
              : 'Enter the recipient identity from the configured identity provider.'}
          </DialogDescription>
        </DialogHeader>
        <form
          className={styles.stackLarge}
          onSubmit={(event) => {
            event.preventDefault()
            if (valid) save.mutate()
          }}
        >
          <div className={styles.stackSmall}>
            <Label htmlFor="grant-issuer">Issuer</Label>
            <Input
              id="grant-issuer"
              autoComplete="off"
              value={draft.issuer}
              disabled={isExisting || save.isPending}
              onChange={(event) =>
                setDraft({ ...draft, issuer: event.target.value })
              }
            />
          </div>
          <div className={styles.stackSmall}>
            <Label htmlFor="grant-subject">Subject ID</Label>
            <Input
              id="grant-subject"
              autoComplete="off"
              value={draft.subject}
              disabled={isExisting || save.isPending}
              onChange={(event) =>
                setDraft({ ...draft, subject: event.target.value })
              }
            />
          </div>
          <div className={styles.stackSmall}>
            <Label htmlFor="grant-display-name">Display name (optional)</Label>
            <Input
              id="grant-display-name"
              autoComplete="off"
              value={draft.displayName ?? ''}
              disabled={save.isPending}
              onChange={(event) =>
                setDraft({ ...draft, displayName: event.target.value || null })
              }
            />
          </div>
          <div className={styles.stackSmall}>
            <Label htmlFor="grant-role">Role</Label>
            <select
              id="grant-role"
              className={styles.field}
              value={draft.role}
              disabled={save.isPending}
              onChange={(event) =>
                setDraft({
                  ...draft,
                  role: event.target.value as ProjectGrant['role'],
                })
              }
            >
              {roles.map((role) => (
                <option key={role} value={role}>
                  {role}
                </option>
              ))}
            </select>
          </div>
          {save.isError && (
            <p role="alert" className={styles.error}>
              {save.error.message}
            </p>
          )}
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              disabled={save.isPending}
              onClick={onClose}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={!valid || save.isPending}>
              {save.isPending
                ? 'Saving…'
                : isExisting
                  ? 'Change role'
                  : 'Grant access'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function RevokeGrantDialog({
  name,
  grant,
  onClose,
}: {
  name: string
  grant: ProjectGrant
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const revoke = useMutation({
    mutationFn: () => deleteProjectGrant(name, grant),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ['projects', name, 'grants'],
      })
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
          <DialogTitle>Revoke project access</DialogTitle>
          <DialogDescription>
            Revoke {grant.displayName ?? grant.subject} from {name}? Their next
            platform request will be denied.
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

export { ProjectGrants }
