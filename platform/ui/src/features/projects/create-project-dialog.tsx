import * as React from 'react'
import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { Button, Group, Modal, Stack, Text, TextInput } from '@mantine/core'

import { createEmptyProject } from '@/features/projects/projects-api'

const projectSchema = z.object({
  name: z
    .string()
    .trim()
    .regex(
      /^[a-z](?:[a-z0-9-]{0,30}[a-z0-9])?$/,
      'Use 1–32 lowercase letters, digits, or hyphens; start with a letter.',
    ),
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
      <Modal
        opened={open}
        onClose={() => handleOpenChange(false)}
        title="Create project"
        centered
        closeOnEscape={!createProject.isPending}
        closeOnClickOutside={!createProject.isPending}
        withCloseButton={!createProject.isPending}
      >
        <Stack gap="md">
          <Text size="sm">
            Creates an empty project and its authorization scope. You can deploy
            an application in the next step.
          </Text>
          <form
            onSubmit={(event) =>
              void form.handleSubmit((values) => createProject.mutate(values))(
                event,
              )
            }
          >
            <Stack gap="md">
              <TextInput
                id="project-name"
                data-autofocus
                label="Project name"
                description="1–32 lowercase letters, digits, or hyphens. Names start with a letter."
                autoComplete="off"
                aria-invalid={Boolean(form.formState.errors.name)}
                {...form.register('name')}
              />
              {form.formState.errors.name && (
                <Text role="alert" size="sm" c="red">
                  {form.formState.errors.name.message}
                </Text>
              )}
              {createProject.isError && (
                <Text role="alert" size="sm" c="red">
                  {createProject.error.message}
                </Text>
              )}
              <Group justify="flex-end">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => handleOpenChange(false)}
                >
                  Cancel
                </Button>
                <Button type="submit" disabled={createProject.isPending}>
                  {createProject.isPending ? 'Creating…' : 'Create project'}
                </Button>
              </Group>
            </Stack>
          </form>
        </Stack>
      </Modal>
    </>
  )
}

export { CreateProjectDialog }
