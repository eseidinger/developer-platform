import * as React from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { updateProjectConfiguration, type OperationAccepted } from '@/features/projects/projects-api'

type Entry = { name: string; value: string }

function EditConfigurationDialog({ name, revision, values, onAccepted }: { name: string; revision: number; values: Record<string, string>; onAccepted: (operation: OperationAccepted) => void }) {
  const [open, setOpen] = React.useState(false)
  const [entries, setEntries] = React.useState<Entry[]>([])
  const [formError, setFormError] = React.useState<string | null>(null)
  const queryClient = useQueryClient()
  const update = useMutation({
    mutationFn: (nextValues: Record<string, string>) => updateProjectConfiguration(name, nextValues, revision),
    onSuccess: async (operation) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['projects', name, 'configuration'] }),
        queryClient.invalidateQueries({ queryKey: ['projects', name, 'revisions'] }),
      ])
      onAccepted(operation)
      setOpen(false)
    },
  })

  function openDialog() {
    setEntries(Object.entries(values).map(([entryName, value]) => ({ name: entryName, value })))
    setFormError(null)
    update.reset()
    setOpen(true)
  }

  function updateEntry(index: number, field: keyof Entry, nextValue: string) {
    setEntries((current) => current.map((entry, currentIndex) => currentIndex === index ? { ...entry, [field]: nextValue } : entry))
  }

  function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const nextValues: Record<string, string> = {}
    for (const entry of entries) {
      const entryName = entry.name.trim()
      if (!entryName) {
        setFormError('Each configuration entry needs a name.')
        return
      }
      if (entryName in nextValues) {
        setFormError(`Configuration name ${entryName} appears more than once.`)
        return
      }
      nextValues[entryName] = entry.value
    }
    setFormError(null)
    update.mutate(nextValues)
  }

  return (
    <>
      <Button variant="outline" onClick={openDialog}>Edit configuration</Button>
      <Dialog open={open} onOpenChange={(nextOpen) => { if (!update.isPending) setOpen(nextOpen) }}>
        <DialogContent className="sm:max-w-xl" showCloseButton={!update.isPending}>
          <DialogHeader><DialogTitle>Edit configuration</DialogTitle><DialogDescription>Changing configuration creates a new revision and restarts the workload. Use Secrets for sensitive values.</DialogDescription></DialogHeader>
          <form className="space-y-3" onSubmit={submit}>
            {entries.map((entry, index) => <div key={index} className="flex gap-2"><Input aria-label={`Configuration name ${index + 1}`} value={entry.name} onChange={(event) => updateEntry(index, 'name', event.target.value)} disabled={update.isPending} placeholder="NAME" /><Input aria-label={`Configuration value ${index + 1}`} value={entry.value} onChange={(event) => updateEntry(index, 'value', event.target.value)} disabled={update.isPending} placeholder="Value" /><Button type="button" variant="outline" onClick={() => setEntries((current) => current.filter((_, currentIndex) => currentIndex !== index))} disabled={update.isPending}>Remove</Button></div>)}
            <Button type="button" variant="outline" onClick={() => setEntries((current) => [...current, { name: '', value: '' }])} disabled={update.isPending}>Add value</Button>
            {formError && <p role="alert" className="text-sm text-destructive">{formError}</p>}
            {update.isError && <p role="alert" className="text-sm text-destructive">{update.error.message}</p>}
            <DialogFooter><Button type="button" variant="outline" onClick={() => setOpen(false)} disabled={update.isPending}>Cancel</Button><Button type="submit" disabled={update.isPending}>{update.isPending ? 'Saving…' : 'Save configuration'}</Button></DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </>
  )
}

export { EditConfigurationDialog }
