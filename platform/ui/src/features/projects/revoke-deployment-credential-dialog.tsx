import * as React from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { revokeDeploymentCredential } from '@/features/projects/projects-api'

function RevokeDeploymentCredentialDialog({ name, credentialId, credentialName }: { name: string; credentialId: string; credentialName: string }) {
  const [open, setOpen] = React.useState(false)
  const queryClient = useQueryClient()
  const revoke = useMutation({
    mutationFn: () => revokeDeploymentCredential(name, credentialId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['projects', name, 'deployment-credentials'] })
      setOpen(false)
    },
  })

  function handleOpenChange(nextOpen: boolean) {
    if (revoke.isPending) return
    setOpen(nextOpen)
    if (!nextOpen) revoke.reset()
  }

  return <><Button size="sm" variant="destructive" onClick={() => setOpen(true)}>Revoke</Button><Dialog open={open} onOpenChange={handleOpenChange}><DialogContent showCloseButton={!revoke.isPending}><DialogHeader><DialogTitle>Revoke {credentialName}</DialogTitle><DialogDescription>This immediately denies the credential platform access. Identity-provider cleanup may complete shortly afterward.</DialogDescription></DialogHeader>{revoke.isError && <p role="alert" className="text-sm text-destructive">{revoke.error.message}</p>}<DialogFooter><Button type="button" variant="outline" onClick={() => handleOpenChange(false)} disabled={revoke.isPending}>Cancel</Button><Button type="button" variant="destructive" onClick={() => revoke.mutate()} disabled={revoke.isPending}>{revoke.isPending ? 'Revoking…' : 'Revoke credential'}</Button></DialogFooter></DialogContent></Dialog></>
}

export { RevokeDeploymentCredentialDialog }
