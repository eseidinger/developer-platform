import * as React from 'react'
import { useQueryClient } from '@tanstack/react-query'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { rotateDeploymentCredential, type OneTimeDeploymentCredential } from '@/features/projects/projects-api'

function RotateDeploymentCredentialDialog({ name, credentialId, credentialName }: { name: string; credentialId: string; credentialName: string }) {
  const [open, setOpen] = React.useState(false)
  const [expiresInDays, setExpiresInDays] = React.useState(30)
  const [overlapHours, setOverlapHours] = React.useState(1)
  const [result, setResult] = React.useState<OneTimeDeploymentCredential | null>(null)
  const [error, setError] = React.useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = React.useState(false)
  const queryClient = useQueryClient()
  function clear() { setExpiresInDays(30); setOverlapHours(1); setResult(null); setError(null) }
  function handleOpenChange(nextOpen: boolean) { if (isSubmitting) return; setOpen(nextOpen); if (!nextOpen) clear() }
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setIsSubmitting(true); setError(null)
    try { const created = await rotateDeploymentCredential(name, credentialId, { expiresInDays, overlapHours }); setResult(created); await queryClient.invalidateQueries({ queryKey: ['projects', name, 'deployment-credentials'] }) } catch (caught) { setError(caught instanceof Error ? caught.message : 'Unable to rotate the deployment credential.') } finally { setIsSubmitting(false) }
  }
  async function copy(value: string) { try { await navigator.clipboard.writeText(value) } catch { setError('Copy failed. Select and copy the value manually.') } }
  return <><Button size="sm" variant="outline" onClick={() => setOpen(true)}>Rotate</Button><Dialog open={open} onOpenChange={handleOpenChange}><DialogContent className="sm:max-w-xl" showCloseButton={!isSubmitting}><DialogHeader><DialogTitle>{result ? 'Save replacement credential' : `Rotate ${credentialName}`}</DialogTitle><DialogDescription>{result ? 'Copy these values now. The replacement secret cannot be retrieved again after closing this dialog.' : 'Creates a replacement credential and limits the predecessor to the selected overlap window.'}</DialogDescription></DialogHeader>{result ? <div className="space-y-3"><CredentialField label="Token endpoint" value={result.tokenEndpoint} onCopy={() => void copy(result.tokenEndpoint)} /><CredentialField label="Client ID" value={result.clientId} onCopy={() => void copy(result.clientId)} /><CredentialField label="Client secret" value={result.clientSecret} onCopy={() => void copy(result.clientSecret)} secret />{error && <p role="alert" className="text-sm text-destructive">{error}</p>}<DialogFooter><Button type="button" onClick={() => handleOpenChange(false)}>I saved these values</Button></DialogFooter></div> : <form className="space-y-4" onSubmit={(event) => void submit(event)}><div className="space-y-2"><Label htmlFor={`rotation-expiry-${credentialId}`}>Replacement lifetime in days</Label><Input id={`rotation-expiry-${credentialId}`} type="number" min="1" max="90" value={expiresInDays} onChange={(event) => setExpiresInDays(Number(event.target.value))} disabled={isSubmitting} /></div><div className="space-y-2"><Label htmlFor={`rotation-overlap-${credentialId}`}>Predecessor overlap in hours</Label><Input id={`rotation-overlap-${credentialId}`} type="number" min="0" max="24" value={overlapHours} onChange={(event) => setOverlapHours(Number(event.target.value))} disabled={isSubmitting} /></div>{error && <p role="alert" className="text-sm text-destructive">{error}</p>}<DialogFooter><Button type="button" variant="outline" onClick={() => handleOpenChange(false)} disabled={isSubmitting}>Cancel</Button><Button type="submit" disabled={isSubmitting}>{isSubmitting ? 'Rotating…' : 'Rotate credential'}</Button></DialogFooter></form>}</DialogContent></Dialog></>
}

function CredentialField({ label, value, onCopy, secret = false }: { label: string; value: string; onCopy: () => void; secret?: boolean }) { return <div className="space-y-2"><Label>{label}</Label><div className="flex gap-2"><Input readOnly type={secret ? 'password' : 'text'} value={value} /><Button type="button" variant="outline" onClick={onCopy}>Copy</Button></div></div> }

export { RotateDeploymentCredentialDialog }
