import * as React from 'react'
import { useQueryClient } from '@tanstack/react-query'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { setProjectSecret } from '@/features/projects/projects-api'

function SetSecretDialog({ name }: { name: string }) {
  const [open, setOpen] = React.useState(false)
  const [secretName, setSecretName] = React.useState('')
  const [value, setValue] = React.useState('')
  const [error, setError] = React.useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = React.useState(false)
  const queryClient = useQueryClient()

  function clear() {
    setSecretName('')
    setValue('')
    setError(null)
  }

  function handleOpenChange(nextOpen: boolean) {
    if (isSubmitting) return
    setOpen(nextOpen)
    if (!nextOpen) clear()
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const trimmedName = secretName.trim()
    if (!trimmedName) {
      setError('Enter a secret name.')
      return
    }
    if (!value) {
      setError('Enter a secret value.')
      return
    }

    setIsSubmitting(true)
    setError(null)
    try {
      await setProjectSecret(name, trimmedName, value)
      clear()
      await queryClient.invalidateQueries({ queryKey: ['projects', name, 'secrets'] })
      setOpen(false)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to save the secret.')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <>
      <Button variant="outline" onClick={() => setOpen(true)}>Set secret</Button>
      <Dialog open={open} onOpenChange={handleOpenChange}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Set project secret</DialogTitle>
            <DialogDescription>The value is sent once and is never shown again. Reusing a name rotates its value and restarts the workload.</DialogDescription>
          </DialogHeader>
          <form className="space-y-4" onSubmit={(event) => void submit(event)}>
            <div className="space-y-2">
              <Label htmlFor="secret-name">Name</Label>
              <Input id="secret-name" autoComplete="off" value={secretName} onChange={(event) => setSecretName(event.target.value)} disabled={isSubmitting} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="secret-value">Value</Label>
              <Input id="secret-value" type="password" autoComplete="new-password" value={value} onChange={(event) => setValue(event.target.value)} disabled={isSubmitting} />
            </div>
            {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => handleOpenChange(false)} disabled={isSubmitting}>Cancel</Button>
              <Button type="submit" disabled={isSubmitting}>{isSubmitting ? 'Saving…' : 'Save secret'}</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </>
  )
}

export { SetSecretDialog }
