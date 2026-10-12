import * as React from 'react'

import { AccessDialog, Check, Field, GroupPicker, RouteSummary, type Accepted } from './access-controls'
import { changeHuman, changeService, getHumanRequests, getServices, IdempotentIntent, requestService, requireVersion, type Group, type HumanAction, type HumanRequest, type Policy, type ServiceAccess, type ServiceAction } from './access-api'

const humanLabels: Record<HumanAction, string> = { approve: 'Approve human request', groups: 'Add application groups', reject: 'Reject human request', cancel: 'Cancel human request', reopen: 'Reopen human request' }
export function HumanActionDialog({ project, resource, action, groups, policy, onAccepted, onClose }: { project: string; resource: HumanRequest; action: HumanAction; groups: Group[]; policy: Policy | null; onAccepted: Accepted; onClose: () => void }) {
  const [selected, setSelected] = React.useState<string[]>([])
  const granting = action === 'approve' || action === 'groups'
  const title = humanLabels[action]
  async function reload() {
    const current = (await getHumanRequests(project)).find((r) => r.id === resource.id)
    if (!current) throw new Error('This request is no longer available.')
    return current
  }
  return <AccessDialog title={title} description={`${resource.spec.principalId} requests access to ${project}. Platform roles assign no application groups.`} submitLabel={title} resource={resource} reload={reload} canSubmit={!granting || selected.length > 0} destructive={action === 'reject' || action === 'cancel'} onAccepted={onAccepted} onClose={onClose} submit={(version) => changeHuman(project, resource.id, requireVersion(version), action, selected)}>
    <dl className="space-y-1 break-all text-sm"><dt>Request</dt><dd>{resource.id}</dd><dt>Identity issuer / subject</dt><dd>{resource.spec.issuer} / {resource.spec.subject}</dd><dt>Expires</dt><dd>{resource.spec.expiresAt}</dd><dt>State</dt><dd>{resource.state}</dd></dl>
    {granting && <><GroupPicker groups={groups.filter((g) => g.state === 'active')} selected={selected} onChange={setSelected} />{policy && <RouteSummary policy={policy.spec} groups={groups} selected={selected} />}<p>Approval creates memberships that remain provisioning until confirmed by the identity provider. The person then refreshes the application session or signs in again.</p></>}
    {action === 'reopen' && <p>This returns the request to pending with a new 30-day expiry. It grants no membership.</p>}
  </AccessDialog>
}

export function RequestServiceDialog({ project, onAccepted, onClose }: { project: string; onAccepted: Accepted; onClose: () => void }) {
  const [name, setName] = React.useState('')
  const [provider, setProvider] = React.useState('')
  const [application, setApplication] = React.useState('')
  const [acknowledged, setAcknowledged] = React.useState(false)
  const [intent] = React.useState(() => new IdempotentIntent())
  const slug = /^[a-z](?:[a-z0-9-]{0,30}[a-z0-9])?$/
  return <AccessDialog title="Request service access" description="The provider must approve application groups before a service credential is provisioned." submitLabel="Request access" canSubmit={acknowledged && [name, provider, application].every((v) => slug.test(v))} onAccepted={onAccepted} onClose={onClose} submit={() => {
    const body = { name, providerProject: provider, application, projectWideCredential: true as const }
    return requestService(project, body, intent.keyFor(body))
  }}>
    <Field label="Request name" required maxLength={32} value={name} onChange={(e) => setName(e.target.value)} />
    <Field label="Provider project" required maxLength={32} value={provider} onChange={(e) => { setProvider(e.target.value); setApplication(e.target.value) }} />
    <Field label="Target application" required maxLength={32} value={application} onChange={(e) => setApplication(e.target.value)} />
    <Check label="I understand every component in this consumer project can use the managed credential" checked={acknowledged} onChange={(e) => setAcknowledged(e.target.checked)} />
    <p>No provider groups are assigned by this request. The target must have an active bearer-token policy.</p>
  </AccessDialog>
}
const serviceLabels: Record<ServiceAction, string> = { approve: 'Approve service request', reject: 'Reject service request', cancel: 'Cancel service request', rotate: 'Rotate service credential', emergency: 'Emergency rotation', confirm: 'Confirm credential adoption', revoke: 'Revoke service access' }
export function ServiceActionDialog({ project, resource, action, groups, policy, onAccepted, onClose }: { project: string; resource: ServiceAccess; action: ServiceAction; groups: Group[]; policy: Policy | null; onAccepted: Accepted; onClose: () => void }) {
  const [selected, setSelected] = React.useState<string[]>([])
  const allowed = new Set(policy?.spec.routes.filter((r) => r.authentication.mode === 'bearer-token').flatMap((r) => r.authorization.anyOfGroups) ?? [])
  const eligibleGroups = groups.filter((g) => g.state === 'active' && allowed.has(g.id))
  async function reload() {
    const current = (await getServices(project)).find((r) => r.id === resource.id)
    if (!current) throw new Error('This service request is no longer available.')
    return current
  }
  return <AccessDialog title={serviceLabels[action]} description={`Consumer ${resource.project} → ${resource.spec.providerProject}/${resource.spec.application}. Credential access is project-wide.`} submitLabel={serviceLabels[action]} resource={resource} reload={reload} canSubmit={action !== 'approve' || selected.length > 0} destructive={['reject', 'cancel', 'emergency', 'revoke'].includes(action)} onAccepted={onAccepted} onClose={onClose} submit={(version) => changeService(project, resource.id, requireVersion(version), action, selected)}>
    <p className="break-all text-sm">Request {resource.id}; state {resource.state}.</p>
    {action === 'approve' && <><GroupPicker groups={eligibleGroups} selected={selected} onChange={setSelected} />{policy && <RouteSummary policy={{ ...policy.spec, routes: policy.spec.routes.filter((r) => r.authentication.mode === 'bearer-token') }} groups={groups} selected={selected} />}<p>Only target bearer-route groups can be assigned. Approval begins credential provisioning; it does not return a client secret.</p></>}
    {action === 'rotate' && <p>The replacement goes to the managed project secret. Adopt it and confirm here. The old client overlaps for at most 24 hours, then is revoked automatically.</p>}
    {action === 'emergency' && <p>The old client loses authority immediately, with no overlap. Calls may be interrupted while the replacement is provisioned.</p>}
    {action === 'confirm' && <p>Confirm that the consumer has adopted the replacement credential. This revokes the previous client.</p>}
    {action === 'revoke' && <p>New requests lose authority within the five-minute bound. Provider client and managed secret cleanup continues asynchronously.</p>}
  </AccessDialog>
}
