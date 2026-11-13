import styles from './project-dialogs.module.css'
import * as React from 'react'
import { useQueryClient } from '@tanstack/react-query'

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
import {
  createDeploymentCredential,
  type OneTimeDeploymentCredential,
} from '@/features/projects/projects-api'

function CreateDeploymentCredentialDialog({ name }: { name: string }) {
  const [open, setOpen] = React.useState(false)
  const [credentialName, setCredentialName] = React.useState('')
  const [expiresInDays, setExpiresInDays] = React.useState(30)
  const [result, setResult] =
    React.useState<OneTimeDeploymentCredential | null>(null)
  const [error, setError] = React.useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = React.useState(false)
  const queryClient = useQueryClient()

  function clear() {
    setCredentialName('')
    setExpiresInDays(30)
    setResult(null)
    setError(null)
  }

  function handleOpenChange(nextOpen: boolean) {
    if (isSubmitting) return
    setOpen(nextOpen)
    if (!nextOpen) clear()
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!credentialName.trim()) {
      setError('Enter a credential name.')
      return
    }
    setIsSubmitting(true)
    setError(null)
    try {
      const created = await createDeploymentCredential(name, {
        name: credentialName.trim(),
        expiresInDays,
      })
      setResult(created)
      await queryClient.invalidateQueries({
        queryKey: ['projects', name, 'deployment-credentials'],
      })
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : 'Unable to create the deployment credential.',
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  async function copy(value: string) {
    try {
      await navigator.clipboard.writeText(value)
    } catch {
      setError('Copy failed. Select and copy the value manually.')
    }
  }

  return (
    <>
      <Button variant="outline" onClick={() => setOpen(true)}>
        Create credential
      </Button>
      <Dialog open={open} onOpenChange={handleOpenChange}>
        <DialogContent
          className={styles.wideModal}
          showCloseButton={!isSubmitting}
        >
          <DialogHeader>
            <DialogTitle>
              {result
                ? 'Save deployment credential'
                : 'Create deployment credential'}
            </DialogTitle>
            <DialogDescription>
              {result
                ? 'Copy these values now. The client secret cannot be retrieved again after closing this dialog.'
                : 'Creates a project-scoped OIDC client for deployment automation.'}
            </DialogDescription>
          </DialogHeader>
          {result ? (
            <div className={styles.stackMedium}>
              <CredentialField
                label="Token endpoint"
                value={result.tokenEndpoint}
                onCopy={() => void copy(result.tokenEndpoint)}
              />
              <CredentialField
                label="Client ID"
                value={result.clientId}
                onCopy={() => void copy(result.clientId)}
              />
              <CredentialField
                label="Client secret"
                value={result.clientSecret}
                onCopy={() => void copy(result.clientSecret)}
                secret
              />
              {error && (
                <p role="alert" className={styles.error}>
                  {error}
                </p>
              )}
              <DialogFooter>
                <Button type="button" onClick={() => handleOpenChange(false)}>
                  I saved these values
                </Button>
              </DialogFooter>
            </div>
          ) : (
            <form
              className={styles.stackLarge}
              onSubmit={(event) => void submit(event)}
            >
              <div className={styles.stackSmall}>
                <Label htmlFor="credential-name">Credential name</Label>
                <Input
                  id="credential-name"
                  autoComplete="off"
                  value={credentialName}
                  onChange={(event) => setCredentialName(event.target.value)}
                  disabled={isSubmitting}
                />
              </div>
              <div className={styles.stackSmall}>
                <Label htmlFor="credential-expiry">Expires in days</Label>
                <Input
                  id="credential-expiry"
                  type="number"
                  min="1"
                  max="90"
                  value={expiresInDays}
                  onChange={(event) =>
                    setExpiresInDays(Number(event.target.value))
                  }
                  disabled={isSubmitting}
                />
              </div>
              {error && (
                <p role="alert" className={styles.error}>
                  {error}
                </p>
              )}
              <DialogFooter>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => handleOpenChange(false)}
                  disabled={isSubmitting}
                >
                  Cancel
                </Button>
                <Button type="submit" disabled={isSubmitting}>
                  {isSubmitting ? 'Creating…' : 'Create credential'}
                </Button>
              </DialogFooter>
            </form>
          )}
        </DialogContent>
      </Dialog>
    </>
  )
}

function CredentialField({
  label,
  value,
  onCopy,
  secret = false,
}: {
  label: string
  value: string
  onCopy: () => void
  secret?: boolean
}) {
  return (
    <div className={styles.stackSmall}>
      <Label>{label}</Label>
      <div className={styles.actions}>
        <Input readOnly type={secret ? 'password' : 'text'} value={value} />
        <Button type="button" variant="outline" onClick={onCopy}>
          Copy
        </Button>
      </div>
    </div>
  )
}

export { CreateDeploymentCredentialDialog }
