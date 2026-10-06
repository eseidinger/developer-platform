import * as React from 'react'
import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { z } from 'zod'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { deployProject, type OperationAccepted } from '@/features/projects/projects-api'

const deploymentSchema = z.object({
  image: z.string().trim().min(1, 'Enter a container image.').max(512),
  port: z.number().int().min(1024, 'Use a port from 1024 through 65535.').max(65535, 'Use a port from 1024 through 65535.'),
  probe_profile: z.enum(['status', 'hello-world']),
})

type DeploymentFormValues = z.infer<typeof deploymentSchema>

function DeployProjectDialog({ name, onAccepted }: { name: string; onAccepted: (operation: OperationAccepted) => void }) {
  const [open, setOpen] = React.useState(false)
  const queryClient = useQueryClient()
  const form = useForm<DeploymentFormValues>({
    defaultValues: { image: 'hashicorp/http-echo:1.0.0', port: 5678, probe_profile: 'status' },
    resolver: zodResolver(deploymentSchema),
  })
  const deployment = useMutation({
    mutationFn: (values: DeploymentFormValues) => deployProject(name, { name, ...values }),
    onSuccess: async (operation) => {
      await queryClient.invalidateQueries({ queryKey: ['projects', name, 'revisions'] })
      await queryClient.invalidateQueries({ queryKey: ['projects'] })
      onAccepted(operation)
      setOpen(false)
    },
  })

  function handleOpenChange(nextOpen: boolean) {
    if (deployment.isPending) return
    setOpen(nextOpen)
    if (!nextOpen) deployment.reset()
  }

  return (
    <>
      <Button onClick={() => setOpen(true)}>Deploy application</Button>
      <Dialog open={open} onOpenChange={handleOpenChange}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Deploy application</DialogTitle>
            <DialogDescription>Submit a new desired revision for {name}.</DialogDescription>
          </DialogHeader>
          <form className="space-y-4" onSubmit={(event) => void form.handleSubmit((values) => deployment.mutate(values))(event)}>
            <div className="space-y-2">
              <Label htmlFor="deployment-image">Container image</Label>
              <Input id="deployment-image" autoComplete="off" aria-invalid={Boolean(form.formState.errors.image)} {...form.register('image')} />
              {form.formState.errors.image && <p role="alert" className="text-sm text-destructive">{form.formState.errors.image.message}</p>}
            </div>
            <div className="space-y-2">
              <Label htmlFor="deployment-port">Port</Label>
              <Input id="deployment-port" type="number" min="1024" max="65535" aria-invalid={Boolean(form.formState.errors.port)} {...form.register('port', { valueAsNumber: true })} />
              {form.formState.errors.port && <p role="alert" className="text-sm text-destructive">{form.formState.errors.port.message}</p>}
            </div>
            <div className="space-y-2">
              <Label htmlFor="deployment-probe">Probe profile</Label>
              <select id="deployment-probe" className="h-8 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm" {...form.register('probe_profile')}>
                <option value="status">HTTP 200 status</option>
                <option value="hello-world">hello-world response</option>
              </select>
            </div>
            {deployment.isError && <p role="alert" className="text-sm text-destructive">{deployment.error.message}</p>}
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => handleOpenChange(false)}>Cancel</Button>
              <Button type="submit" disabled={deployment.isPending}>{deployment.isPending ? 'Submitting…' : 'Deploy'}</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </>
  )
}

export { DeployProjectDialog }
