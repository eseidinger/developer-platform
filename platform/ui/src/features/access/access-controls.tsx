import * as React from 'react'
import { useMutation } from '@tanstack/react-query'

import { ApiError } from '@/api/errors'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import type { Group, Policy, Resource } from './access-api'
import { AccessEvents } from './access-events'

export const selectClass =
  'min-h-9 w-full rounded-lg border border-input bg-background px-2 text-sm'
export function Field({
  label,
  ...props
}: React.ComponentProps<typeof Input> & { label: string }) {
  const id = React.useId()
  return (
    <div className="space-y-1">
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} {...props} />
    </div>
  )
}
export function Choice({
  label,
  children,
  ...props
}: React.ComponentProps<'select'> & { label: string }) {
  const id = React.useId()
  return (
    <div className="space-y-1">
      <Label htmlFor={id}>{label}</Label>
      <select id={id} className={selectClass} {...props}>
        {children}
      </select>
    </div>
  )
}
export function Check({
  label,
  ...props
}: React.ComponentProps<'input'> & { label: string }) {
  return (
    <label className="flex items-start gap-2 text-sm">
      <input className="mt-1 size-4 shrink-0" type="checkbox" {...props} />
      <span>{label}</span>
    </label>
  )
}
export function GroupPicker({
  groups,
  selected,
  onChange,
  label = 'Application groups',
}: {
  groups: Group[]
  selected: string[]
  onChange: (groups: string[]) => void
  label?: string
}) {
  return (
    <fieldset className="space-y-2 rounded-lg border border-border p-3">
      <legend className="px-1 font-medium">{label}</legend>
      {groups.length ? (
        groups.map((group) => (
          <Check
            key={group.id}
            label={`${group.spec.displayName} (${group.name})`}
            checked={selected.includes(group.id)}
            onChange={(event) =>
              onChange(
                event.target.checked
                  ? [...selected, group.id]
                  : selected.filter((id) => id !== group.id),
              )
            }
          />
        ))
      ) : (
        <p>
          No eligible groups. Create groups and configure the target policy
          first.
        </p>
      )}
      <p className="text-xs text-muted-foreground">
        Membership in any selected group permits the matching routes.
      </p>
    </fieldset>
  )
}
export function RouteSummary({
  policy,
  groups,
  selected,
}: {
  policy: Policy['spec']
  groups: Group[]
  selected?: string[]
}) {
  const routes = selected
    ? policy.routes.filter((r) =>
        r.authorization.anyOfGroups.some((id) => selected.includes(id)),
      )
    : policy.routes
  return (
    <div className="space-y-2 rounded-lg bg-muted p-3 text-sm">
      <p className="font-medium">Permitted routes</p>
      {routes.length ? (
        <ul className="space-y-2">
          {routes.map((route) => (
            <li key={route.name} className="break-words">
              <span className="font-medium">{route.name}</span>:{' '}
              {route.match.methods.join(', ')}{' '}
              {route.match.path ?? route.match.pathPrefix} (
              {route.match.path ? 'exact' : 'segment prefix'}),{' '}
              {route.authentication.mode}; groups{' '}
              {route.authorization.anyOfGroups
                .map((id) => groups.find((g) => g.id === id)?.name ?? id)
                .join(', ')}
            </li>
          ))}
        </ul>
      ) : (
        <p>No current route permits the selected groups.</p>
      )}
      <p>All unmatched requests are denied.</p>
    </div>
  )
}
type Versioned = Pick<Resource, 'id' | 'version' | 'state'>
export type Accepted = (result: Versioned) => Promise<void>
export type Reload = () => Promise<Versioned | null>

export function AccessDialog({
  title,
  description,
  submitLabel,
  resource,
  reload,
  submit,
  onAccepted,
  onClose,
  canSubmit = true,
  destructive = false,
  children,
}: {
  title: string
  description: string
  submitLabel: string
  resource?: Versioned | null
  reload?: Reload
  submit: (version: number | undefined) => Promise<Versioned>
  onAccepted: Accepted
  onClose: () => void
  canSubmit?: boolean
  destructive?: boolean
  children?: React.ReactNode
}) {
  const [version, setVersion] = React.useState(resource?.version)
  const [current, setCurrent] = React.useState<Versioned | null>(null)
  const [reloading, setReloading] = React.useState(false)
  const [reloadError, setReloadError] = React.useState<string | null>(null)
  const [reloadRequired, setReloadRequired] = React.useState(false)
  // A synchronous latch prevents duplicate submissions before React rerenders.
  const submitting = React.useRef(false)
  const returnFocus = React.useRef<HTMLElement | null>(
    typeof document !== 'undefined' &&
      document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null,
  )
  const { onDenied } = React.useContext(AccessEvents)
  const mutation = useMutation({
    mutationFn: () => submit(version),
    onSuccess: async (result) => {
      await onAccepted(result)
      onClose()
    },
    onError: (error) => {
      if (error instanceof ApiError && [401, 403].includes(error.status))
        onDenied()
      if (
        error instanceof ApiError &&
        [409, 412, 428].includes(error.status) &&
        reload
      )
        setReloadRequired(true)
    },
    onSettled: () => {
      submitting.current = false
    },
  })
  async function reloadCurrent() {
    if (!reload) return
    setReloading(true)
    setReloadError(null)
    try {
      const result = await reload()
      setVersion(result?.version)
      setCurrent(result)
      setReloadRequired(false)
      mutation.reset()
    } catch (error) {
      setReloadError(
        error instanceof Error
          ? error.message
          : 'Unable to reload current access state.',
      )
    } finally {
      setReloading(false)
    }
  }
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !mutation.isPending && !reloading) onClose()
      }}
    >
      <DialogContent
        className="max-h-[90dvh] overflow-y-auto sm:max-w-2xl"
        showCloseButton={!mutation.isPending && !reloading}
        finalFocus={() =>
          returnFocus.current?.isConnected
            ? returnFocus.current
            : document.getElementById('application-access-title')
        }
      >
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault()
            if (
              canSubmit &&
              !reloadRequired &&
              !reloading &&
              !submitting.current
            ) {
              submitting.current = true
              mutation.mutate()
            }
          }}
        >
          <fieldset
            disabled={mutation.isPending || reloading}
            className="space-y-4"
          >
            {children}
          </fieldset>
          {current && (
            <p role="status">
              Current state: {current.state}, version {current.version}. Your
              draft is preserved; review it before submitting again.
            </p>
          )}
          {mutation.isError && (
            <p role="alert" className="text-sm text-destructive">
              {mutation.error.message}
            </p>
          )}
          {reloadRequired && (
            <div className="space-y-2">
              <p>
                The resource changed or the action conflicts with its state.
                Reload and review before submitting again.
              </p>
              <Button
                type="button"
                variant="outline"
                disabled={reloading}
                onClick={() => void reloadCurrent()}
              >
                {reloading ? 'Reloading…' : 'Reload current version'}
              </Button>
            </div>
          )}
          {reloadError && (
            <p role="alert" className="text-sm text-destructive">
              {reloadError}
            </p>
          )}
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              disabled={mutation.isPending || reloading}
              onClick={onClose}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              variant={destructive ? 'destructive' : 'default'}
              disabled={
                !canSubmit || reloadRequired || mutation.isPending || reloading
              }
            >
              {mutation.isPending ? 'Submitting…' : submitLabel}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
