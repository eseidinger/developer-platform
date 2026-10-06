import * as React from 'react'
import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { z } from 'zod'

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
import { createEmptyProject } from '@/features/projects/projects-api'

const projectSchema = z.object({
  name: z
    .string()
    .trim()
    .regex(/^[a-z](?:[a-z0-9-]{0,30}[a-z0-9])?$/, 'Use 1–32 lowercase letters, digits, or hyphens; start with a letter.'),
})

type ProjectFormValues = z.infer<typeof projectSchema>

function CreateProjectDialog() {
  const [open, setOpen] = React.useState(false)
  const queryClient = useQueryClient()
  const form = useForm<ProjectFormValues>({
    defaultValues: { name: '' },
    resolver: zodResolver(projectSchema),
  })
  const createProject = useMutation({
    mutationFn: createEmptyProject,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['projects'] })
      form.reset()
      setOpen(false)
    },
  })

  function handleOpenChange(nextOpen: boolean) {
    if (createProject.isPending) {
      return
    }

    setOpen(nextOpen)
    if (!nextOpen) {
      form.reset()
      createProject.reset()
    }
  }

  return (
    <>
      <Button onClick={() => setOpen(true)}>New project</Button>
      <Dialog open={open} onOpenChange={handleOpenChange}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create project</DialogTitle>
            <DialogDescription>
              Creates an empty project and its authorization scope. You can deploy an application in the next step.
            </DialogDescription>
          </DialogHeader>
          <form
            className="space-y-4"
            onSubmit={(event) => void form.handleSubmit((values) => createProject.mutate(values))(event)}
          >
            <div className="space-y-2">
              <Label htmlFor="project-name">Project name</Label>
              <Input
                id="project-name"
                autoComplete="off"
                aria-describedby="project-name-help"
                aria-invalid={Boolean(form.formState.errors.name)}
                {...form.register('name')}
              />
              <p id="project-name-help" className="text-xs text-muted-foreground">
                1–32 lowercase letters, digits, or hyphens. Names start with a letter.
              </p>
              {form.formState.errors.name && (
                <p role="alert" className="text-sm text-destructive">
                  {form.formState.errors.name.message}
                </p>
              )}
            </div>
            {createProject.isError && (
              <p role="alert" className="text-sm text-destructive">
                {createProject.error.message}
              </p>
            )}
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => handleOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={createProject.isPending}>
                {createProject.isPending ? 'Creating…' : 'Create project'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </>
  )
}

export { CreateProjectDialog }
