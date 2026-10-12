import * as React from 'react'

import { Button } from '@/components/ui/button'
import { AccessDialog, Check, Choice, Field, GroupPicker, RouteSummary, type Accepted } from './access-controls'
import { createGroup, getGovernance, getPolicy, governanceSchema, IdempotentIntent, saveGovernance, savePolicy, type Governance, type GovernanceInput, type Group, type Policy, type PolicyInput, type RouteInput } from './access-api'
import { httpMethods, validatePolicy } from './policy-validation'

export function CreateGroupDialog({ project, onAccepted, onClose }: { project: string; onAccepted: Accepted; onClose: () => void }) {
  const [name, setName] = React.useState('')
  const [displayName, setDisplayName] = React.useState('')
  const [intent] = React.useState(() => new IdempotentIntent())
  const valid = /^[a-z](?:[a-z0-9-]{0,30}[a-z0-9])?$/.test(name) && Boolean(displayName.trim()) && displayName.length <= 100
  return <AccessDialog title="Create application group" description="Creating a group assigns no memberships. Choose a stable name for policy references." submitLabel="Create group" canSubmit={valid} onAccepted={onAccepted} onClose={onClose} submit={() => { const body = { name, displayName }; return createGroup(project, body, intent.keyFor(body)) }}>
    <Field label="Group name" required maxLength={32} value={name} onChange={(e) => setName(e.target.value)} />
    <p className="text-xs text-muted-foreground">Use lowercase letters, digits and hyphens. Start with a letter and end with a letter or digit.</p>
    <Field label="Display name" required maxLength={100} value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
  </AccessDialog>
}
const emptyGovernance: GovernanceInput = { maximumDataClassification: 'Internal', maximumTelemetryClassification: 'Internal', personalData: false, domainRetentionOwner: '', domainRetentionPolicy: '', purgeAuthority: '', recoveryOwner: '' }
export function GovernanceDialog({ project, resource, onAccepted, onClose }: { project: string; resource: Governance | null; onAccepted: Accepted; onClose: () => void }) {
  const [draft, setDraft] = React.useState<GovernanceInput>(resource?.spec ?? emptyGovernance)
  const valid = governanceSchema.safeParse(draft).success
  return <AccessDialog title="Project governance" description="Record data handling and retention ownership separately from deployment settings." submitLabel="Save governance" resource={resource} reload={() => getGovernance(project)} canSubmit={valid} onAccepted={onAccepted} onClose={onClose} submit={(version) => saveGovernance(project, draft, version)}>
    <Choice label="Maximum data classification" value={draft.maximumDataClassification} onChange={(e) => setDraft({ ...draft, maximumDataClassification: e.target.value as GovernanceInput['maximumDataClassification'] })}>{['Public', 'Internal', 'Confidential'].map((v) => <option key={v}>{v}</option>)}</Choice>
    <Choice label="Maximum telemetry classification" value={draft.maximumTelemetryClassification} onChange={(e) => setDraft({ ...draft, maximumTelemetryClassification: e.target.value as GovernanceInput['maximumTelemetryClassification'] })}>{['Public', 'Internal', 'Confidential'].map((v) => <option key={v}>{v}</option>)}</Choice>
    <Check label="Personal data is handled by this project" checked={draft.personalData} onChange={(e) => setDraft({ ...draft, personalData: e.target.checked })} />
    <Field label="Domain retention owner" required maxLength={200} value={draft.domainRetentionOwner} onChange={(e) => setDraft({ ...draft, domainRetentionOwner: e.target.value })} />
    <Field label="Domain retention policy" required maxLength={2000} value={draft.domainRetentionPolicy} onChange={(e) => setDraft({ ...draft, domainRetentionPolicy: e.target.value })} />
    <Field label="Purge authority" required maxLength={200} value={draft.purgeAuthority} onChange={(e) => setDraft({ ...draft, purgeAuthority: e.target.value })} />
    <Field label="Recovery owner" required maxLength={200} value={draft.recoveryOwner} onChange={(e) => setDraft({ ...draft, recoveryOwner: e.target.value })} />
  </AccessDialog>
}
function emptyRoute(): RouteInput { return { name: '', match: { pathPrefix: '/', methods: ['GET'] }, authentication: { mode: 'browser-session' }, authorization: { anyOfGroups: [] } } }

export function PolicyDialog({ project, component, resource, groups, personalData, modes, onAccepted, onClose }: {
  project: string; component: string; resource: Policy | null; groups: Group[]; personalData: boolean; modes: ('browser-session' | 'bearer-token')[]; onAccepted: Accepted; onClose: () => void;
}) {
  const [draft, setDraft] = React.useState<PolicyInput>(() => resource ? { component, defaultDecision: 'deny', identityAttributes: resource.spec.identityAttributes, routes: resource.spec.routes } : { component, defaultDecision: 'deny', identityAttributes: { displayName: false, email: false }, routes: [emptyRoute()] })
  const [reviewed, setReviewed] = React.useState(false)
  const [errors, setErrors] = React.useState<string[]>([])
  function update(next: PolicyInput) { setDraft(next); setReviewed(false); setErrors([]) }
  function updateRoute(index: number, route: RouteInput) { update({ ...draft, routes: draft.routes.map((r, i) => i === index ? route : r) }) }
  const permitted = !draft.identityAttributes?.email || personalData
  return <AccessDialog title="Application access policy" description={`Configure routes for ${component}. Public exposure alone does not grant access.`} submitLabel="Save policy" resource={resource} reload={() => getPolicy(project)} canSubmit={reviewed && permitted} onAccepted={onAccepted} onClose={onClose} submit={(version) => savePolicy(project, draft, version)}>
    <p className="text-sm">Public component: <strong>{component}</strong>. All unmatched requests are denied. Include entry pages, assets and browser API calls. HEAD follows GET; OPTIONS must be selected explicitly.</p>
    <Check label="Release display name to the application" checked={draft.identityAttributes?.displayName ?? false} onChange={(e) => update({ ...draft, identityAttributes: { displayName: e.target.checked, email: draft.identityAttributes?.email ?? false } })} />
    <Check label="Release email to the application" disabled={!personalData && !draft.identityAttributes?.email} checked={draft.identityAttributes?.email ?? false} onChange={(e) => update({ ...draft, identityAttributes: { displayName: draft.identityAttributes?.displayName ?? false, email: e.target.checked } })} />
    {!personalData && <p className="text-xs text-muted-foreground">Email release requires saved governance covering personal data.</p>}
    {draft.routes.map((route, index) => <fieldset key={index} className="space-y-3 rounded-lg border border-border p-4"><legend className="px-1 font-medium">Rule {index + 1}</legend>
      <Field label={`Rule ${index + 1} name`} required maxLength={64} value={route.name} onChange={(e) => updateRoute(index, { ...route, name: e.target.value })} />
      <Choice label={`Rule ${index + 1} path matching`} value={route.match.path != null ? 'exact' : 'prefix'} onChange={(e) => updateRoute(index, { ...route, match: { methods: route.match.methods, ...(e.target.value === 'exact' ? { path: route.match.pathPrefix ?? '/' } : { pathPrefix: route.match.path ?? '/' }) } })}><option value="exact">Exact path</option><option value="prefix">Segment-aware prefix</option></Choice>
      <Field label={`Rule ${index + 1} path`} required maxLength={2048} value={route.match.path ?? route.match.pathPrefix ?? ''} onChange={(e) => updateRoute(index, { ...route, match: { methods: route.match.methods, ...(route.match.path != null ? { path: e.target.value } : { pathPrefix: e.target.value }) } })} />
      <fieldset className="flex flex-wrap gap-3"><legend className="mb-1">HTTP methods</legend>{httpMethods.map((method) => <Check key={method} label={method} checked={route.match.methods.includes(method)} onChange={(e) => updateRoute(index, { ...route, match: { ...route.match, methods: e.target.checked ? [...route.match.methods, method] : route.match.methods.filter((m) => m !== method) } })} />)}</fieldset>
      <Choice label={`Rule ${index + 1} authentication`} value={route.authentication.mode} onChange={(e) => updateRoute(index, { ...route, authentication: { mode: e.target.value as RouteInput['authentication']['mode'] } })}>{modes.map((mode) => <option value={mode} key={mode}>{mode === 'browser-session' ? 'Browser session' : 'Bearer token'}</option>)}</Choice>
      <GroupPicker groups={groups.filter((g) => g.state === 'active')} selected={route.authorization.anyOfGroups} onChange={(ids) => updateRoute(index, { ...route, authorization: { anyOfGroups: ids } })} label={`Rule ${index + 1} groups`} />
      <Button type="button" variant="outline" onClick={() => update({ ...draft, routes: draft.routes.filter((_, i) => i !== index) })}>Remove rule {index + 1}</Button>
    </fieldset>)}
    <div className="flex flex-wrap gap-2"><Button type="button" variant="outline" disabled={draft.routes.length >= 100} onClick={() => update({ ...draft, routes: [...draft.routes, emptyRoute()] })}>Add route rule</Button><Button type="button" onClick={() => { const problems = validatePolicy(draft); if (!permitted) problems.push('Save personal-data governance before releasing email.'); setErrors(problems); setReviewed(problems.length === 0) }}>Review policy</Button></div>
    {errors.length > 0 && <ul role="alert" className="list-inside list-disc text-destructive">{errors.map((error, i) => <li key={i}>{error}</li>)}</ul>}
    {reviewed && <RouteSummary policy={{ ...draft, identityAttributes: { displayName: draft.identityAttributes?.displayName ?? false, email: draft.identityAttributes?.email ?? false }, defaultDecision: 'deny', host: resource?.spec.host ?? '' }} groups={groups} />}
  </AccessDialog>
}
