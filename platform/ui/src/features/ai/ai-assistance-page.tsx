import { useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { z } from 'zod'
import { useAuth } from '@/auth/auth-context'
import { ApiError } from '@/api/errors'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import { aiKey, approveProposal, classifications, createProposal, createRun, executeProposal, getContext, getProposal, getProposals, getRun, getRuns, kinds, setPolicy, type Proposal, type Run } from './ai-api'

const sectionClass = 'space-y-4 rounded-xl border border-border bg-card p-5'
const uuid = (value: string | null) => z.uuid().safeParse(value).success ? value! : undefined
function QueryMessage({ query, label }: { query: { isPending: boolean; isError: boolean; error: Error | null }; label: string }) {
  if (query.isError) return <p role="alert">{label}: {query.error?.message} Use Refresh AI to check again.</p>
  if (query.isPending) return <p role="status">Loading {label.toLowerCase()}…</p>
  return null
}
export function AiAssistancePage() {
  const { name } = useParams()
  const { status } = useAuth()
  if (!name) return null
  if (status !== 'authenticated') return <section><h1 className="text-3xl font-semibold">AI assistance</h1><p>Sign in to view this project's AI assistance.</p></section>
  return <AiWorkspace key={name} project={name} />
}

type Confirmation = { action: 'approve' | 'execute'; proposal: Proposal } | { action: 'policy' }
function AiWorkspace({ project }: { project: string }) {
  const client = useQueryClient()
  const live = useRef(true)
  const mutationLock = useRef(false)
  const returnFocus = useRef<HTMLElement | null>(null)
  const [params, setParams] = useSearchParams()
  const [busy, setBusy] = useState(false)
  const [denied, setDenied] = useState(false)
  const [uncertain, setUncertain] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null)
  const [projectConfirmation, setProjectConfirmation] = useState('')
  const [classification, setClassification] = useState<typeof classifications[number]>('internal')
  const [now, setNow] = useState(Date.now)
  const [deadline, setDeadline] = useState(() => Date.now() + 300_000)
  const runId = uuid(params.get('run')); const proposalId = uuid(params.get('proposal'))
  const runsBefore = uuid(params.get('runs_before')); const proposalsBefore = uuid(params.get('proposals_before'))
  const key = aiKey(project)
  const context = useQuery({ queryKey: [...key, 'context'], queryFn: ({ signal }) => getContext(project, signal), refetchOnWindowFocus: true })
  const enabled = context.isSuccess
  const polling = now < deadline
  const runs = useQuery({ queryKey: [...key, 'runs', runsBefore], queryFn: ({ signal }) => getRuns(project, runsBefore, signal), enabled,
    refetchInterval: (q) => polling && (busy || uncertain || q.state.data?.items.some((r) => r.state === 'running')) ? 2000 : false })
  const proposals = useQuery({ queryKey: [...key, 'proposals', proposalsBefore], queryFn: ({ signal }) => getProposals(project, proposalsBefore, signal), enabled })
  const run = useQuery({ queryKey: [...key, 'run', runId], queryFn: ({ signal }) => getRun(project, runId!, signal), enabled: enabled && Boolean(runId),
    refetchInterval: (q) => polling && q.state.data?.state === 'running' ? 2000 : false })
  const proposal = useQuery({ queryKey: [...key, 'proposal', proposalId], queryFn: ({ signal }) => getProposal(project, proposalId!, signal), enabled: enabled && Boolean(proposalId),
    refetchInterval: (q) => polling && q.state.data?.state === 'executed' && (!q.state.data.observation || ['queued', 'running'].includes(q.state.data.observation.operation_state) || q.state.data.observation.readiness?.state === 'progressing') ? 2000 : false })
  useEffect(() => { const timer = window.setInterval(() => setNow(Date.now()), 1000); return () => window.clearInterval(timer) }, [])
  useEffect(() => { live.current = true; return () => { live.current = false; void client.cancelQueries({ queryKey: aiKey(project) }); client.removeQueries({ queryKey: aiKey(project) }) } }, [client, project])
  function navigate(values: Record<string, string | undefined>) { if (!live.current) return; setParams((previous) => { const next = new URLSearchParams(previous); for (const [k, v] of Object.entries(values)) { if (v) next.set(k, v); else next.delete(k) } return next }) }
  async function refresh() {
    setDeadline(Date.now() + 300_000)
    const results = await Promise.all([context.refetch(), runs.refetch(), proposals.refetch(), ...(runId ? [run.refetch()] : []), ...(proposalId ? [proposal.refetch()] : [])])
    if (results.every((r) => !r.isError)) { setDenied(false); setUncertain(false) }
  }
  const allowed = enabled && !context.isFetching && !busy && !denied && !uncertain
  const manage = allowed && context.data?.permissions.manage && context.data.external_model_eligible
  const selectedRun = run.isSuccess ? run.data : undefined
  const selectedProposal = proposal.isSuccess ? proposal.data : undefined
  const activeRun = runs.data?.items.some((r) => r.state === 'running') || selectedRun?.state === 'running'
  const eligibleRun = selectedRun?.state === 'completed' && selectedRun.kind === 'investigate_incident' && selectedRun.evidence.length > 0 && selectedRun.base_revision !== null && selectedRun.base_revision === context.data?.current_revision
  const freshProposal = selectedProposal?.base_revision === context.data?.current_revision
  const unexpired = selectedProposal?.expires_at && Date.parse(selectedProposal.expires_at) > now
  async function mutate(action: () => Promise<void>) {
    if (mutationLock.current) return
    mutationLock.current = true
    setDeadline(now + 300_000)
    setBusy(true); setNotice(null)
    try { await action(); if (!live.current) return; setConfirmation(null); setProjectConfirmation(''); await client.invalidateQueries({ queryKey: key }) }
    catch (error) {
      if (!live.current) return
      const known = error instanceof ApiError && [400, 401, 403, 404, 409, 422].includes(error.status)
      setUncertain(!known)
      if (!known) navigate({ runs_before: undefined, proposals_before: undefined })
      if (error instanceof ApiError && [401, 403].includes(error.status)) setDenied(true)
      setNotice(known ? error.message : `${error instanceof ApiError ? error.message + '. ' : ''}The request outcome is unknown. Refresh AI and review durable history before starting another action. The request will not be retried automatically.`)
      setConfirmation(null)
      void client.invalidateQueries({ queryKey: key })
    } finally { mutationLock.current = false; if (live.current) setBusy(false) }
  }
  function openConfirmation(value: Confirmation) { returnFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null; setProjectConfirmation(''); setConfirmation(value) }
  const confirmValid = confirmation?.action === 'policy' ? allowed && context.data?.permissions.edit_policy : manage && selectedProposal && confirmation?.proposal.proposal_id === selectedProposal.proposal_id && confirmation.proposal.diff_sha256 === selectedProposal.diff_sha256 && freshProposal && (confirmation.action === 'approve' ? selectedProposal.state === 'proposed' : selectedProposal.state === 'approved' && unexpired)

  return <section className="max-w-5xl space-y-6 break-words" aria-labelledby="ai-title">
    <header className="space-y-3"><Link className="underline" to={`/projects/${encodeURIComponent(project)}`}>Back to {project}</Link><div className="flex flex-wrap items-center justify-between gap-3"><h1 id="ai-title" tabIndex={-1} className="text-3xl font-semibold">AI assistance</h1><Button variant="outline" disabled={busy} onClick={() => void refresh()}>Refresh AI</Button></div>
      <p>{project}: bounded assistance using authorized project evidence. Results can be incomplete; review their sources.</p></header>
    <QueryMessage query={context} label="AI context" />
    {notice && <p role="alert" className="rounded-lg bg-muted p-3">{notice}</p>}
    {busy && <p role="status">Request in progress. Model requests can take up to two minutes. Navigating away does not cancel server work; reopen history to check the outcome.</p>}
    {!polling && <p role="status">Automatic refresh stopped after five minutes. Use Refresh AI to resume.</p>}
    {enabled && <>
      <section className={sectionClass} aria-labelledby="ai-policy-title"><h2 id="ai-policy-title" className="text-xl font-semibold">Data policy</h2>
        <p>Classification: {context.data.classification ?? 'unclassified'}. External model: {context.data.external_model_eligible ? 'eligible' : 'not eligible'}.</p>
        <p>Runs send minimized Public or Internal project evidence to the configured external model. Provider abuse-monitoring retention may apply. Confidential, Restricted and unclassified projects cannot start runs.</p>
        <p>Current deployment revision: {context.data.current_revision ?? 'none'}.</p>
        {context.data.permissions.edit_policy ? <Button variant="outline" disabled={!allowed} onClick={() => openConfirmation({ action: 'policy' })}>Change classification</Button> : <p className="text-sm text-muted-foreground">A human platform administrator can change classification.</p>}
      </section>
      <section className={sectionClass} aria-labelledby="ai-actions-title"><h2 id="ai-actions-title" className="text-xl font-semibold">Start assistance</h2>
        <div className="flex flex-wrap gap-2">{Object.entries(kinds).map(([kind, label]) => <Button key={kind} disabled={!allowed || !context.data.permissions.run || !context.data.external_model_eligible || activeRun || !runs.isSuccess} onClick={() => void mutate(async () => { navigate({ runs_before: undefined }); const result = await createRun(project, kind as keyof typeof kinds); if (!live.current) return; navigate({ run: result.run_id, runs_before: undefined }); setNotice('Run recorded. Review its result and evidence below.') })}>{label}</Button>)}</div>
        {!context.data.permissions.run && <p>AI runs require a human identity. Automation can only read authorized history.</p>}
        {activeRun && <p role="status">A project run is still marked running. Check its history before starting another model request.</p>}
      </section>
      <section className={sectionClass} aria-labelledby="ai-runs-title"><h2 id="ai-runs-title" className="text-xl font-semibold">Run history</h2><QueryMessage query={runs} label="Run history" />
        {runs.isSuccess && <><ul className="space-y-2">{runs.data.items.map((r) => <li key={r.run_id}><Link className="underline" to={`?${new URLSearchParams({ run: r.run_id, ...(runsBefore ? { runs_before: runsBefore } : {}) })}`}>{kinds[r.kind]} · {r.state} · {r.created_at} · {r.run_id}</Link></li>)}</ul>{!runs.data.items.length && <p>No runs on this page.</p>}
          <Pagination before={runsBefore} next={runs.data.next_cursor} onChange={(value) => navigate({ runs_before: value })} label="runs" /></>}
      </section>
      {runId && <section className={sectionClass} aria-label="Selected run"><QueryMessage query={run} label="Run" />{selectedRun && <><RunResult run={selectedRun} />
        <Button disabled={!manage || !eligibleRun || !proposals.isSuccess} onClick={() => void mutate(async () => { const result = await createProposal(project, selectedRun.run_id); if (!live.current) return; navigate({ proposal: result.proposal_id, proposals_before: undefined }); setNotice('Proposal created. Review the exact diff before approval.') })}>Create rollback proposal</Button>
        {!eligibleRun && <p>A proposal requires a completed, sourced incident investigation bound to the current deployment revision. Older unbound runs remain readable.</p>}
        <p>Proposal creation also requires a server-confirmed failure and a retained successful revision. It does not deploy a change.</p></>}</section>}
      <section className={sectionClass} aria-labelledby="ai-proposals-title"><h2 id="ai-proposals-title" className="text-xl font-semibold">Proposal history</h2><QueryMessage query={proposals} label="Proposal history" />
        {proposals.isSuccess && <><ul className="space-y-2">{proposals.data.items.map((p) => <li key={p.proposal_id}><Link className="underline" to={`?${new URLSearchParams({ proposal: p.proposal_id, ...(proposalsBefore ? { proposals_before: proposalsBefore } : {}) })}`}>Rollback {p.base_revision} → {p.target_revision} · {p.state} · {p.proposal_id}</Link></li>)}</ul>{!proposals.data.items.length && <p>No proposals on this page.</p>}<Pagination before={proposalsBefore} next={proposals.data.next_cursor} onChange={(value) => navigate({ proposals_before: value })} label="proposals" /></>}
      </section>
      {proposalId && <section className={sectionClass} aria-label="Selected proposal"><QueryMessage query={proposal} label="Proposal" />{selectedProposal && <>
        <h2 className="text-xl font-semibold">Review rollback</h2><ProposalReview proposal={selectedProposal} />
        {!freshProposal && selectedProposal.state !== 'executed' && <p role="alert">The base revision is stale. Investigate the current deployment before proposing a change.</p>}
        {selectedProposal.state === 'approved' && !unexpired && <p role="alert">Approval has expired. Execution is disabled.</p>}
        <div className="flex flex-wrap gap-2"><Button disabled={!manage || !freshProposal || selectedProposal.state !== 'proposed'} onClick={() => openConfirmation({ action: 'approve', proposal: selectedProposal })}>Review approval</Button>
          <Button disabled={!manage || !freshProposal || selectedProposal.state !== 'approved' || !unexpired} onClick={() => openConfirmation({ action: 'execute', proposal: selectedProposal })}>Review execution</Button></div>
        {selectedProposal.operation_id && <div className="space-y-2"><h3 className="font-semibold">Recovery observation</h3><p>Operation: {selectedProposal.operation_id} · resulting revision: {selectedProposal.resulting_revision}</p>
          <p>Operation state: {selectedProposal.observation?.operation_state ?? 'not observed'}. Runtime readiness: {selectedProposal.observation?.readiness?.state ?? 'unavailable'}.</p>
          {selectedProposal.observation?.readiness?.reason && <p>Readiness reason: {selectedProposal.observation.readiness.reason}</p>}
          <p>Ready replicas: {selectedProposal.observation?.readiness?.ready_replicas ?? 'unknown'} / {selectedProposal.observation?.readiness?.desired_replicas ?? 'unknown'}.</p>
          <h4 className="font-semibold">Application metrics</h4>{selectedProposal.observation?.metrics ? <MetricObservation metrics={selectedProposal.observation.metrics} /> : <p>Metrics unavailable or not enabled. Operation success alone does not establish application health.</p>}</div>}
      </>}</section>}
    </>}
    <Dialog open={confirmation !== null} onOpenChange={(open) => { if (!open && !busy) setConfirmation(null) }}><DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-2xl" showCloseButton={!busy} finalFocus={() => returnFocus.current?.isConnected && !returnFocus.current.hasAttribute('disabled') ? returnFocus.current : document.getElementById('ai-title')}>
      <DialogTitle>{confirmation?.action === 'policy' ? 'Change data classification' : confirmation?.action === 'approve' ? 'Approve exact rollback diff' : 'Execute approved rollback'}</DialogTitle>
      <DialogDescription>{confirmation?.action === 'policy' ? 'Classification authorizes which minimized project data can reach an external model. A human platform administrator must confirm the project.' : 'Approval and execution are separate human actions. Execution queues a deployment and consumes the approval once.'}</DialogDescription>
      {confirmation?.action === 'policy' ? <label className="space-y-2">Classification<select className="block w-full rounded border p-2" value={classification} onChange={(e) => setClassification(e.target.value as typeof classification)}>{classifications.map((c) => <option key={c}>{c}</option>)}</select></label> : confirmation && <ProposalReview proposal={confirmation.proposal} />}
      <label className="space-y-2">Type {project} to confirm<Input autoComplete="off" value={projectConfirmation} onChange={(e) => setProjectConfirmation(e.target.value)} /></label>
      <div className="flex gap-2"><Button variant="outline" disabled={busy} onClick={() => setConfirmation(null)}>Cancel</Button><Button disabled={busy || projectConfirmation !== project || !confirmValid} onClick={() => void mutate(async () => {
        if (!confirmation) return
        if (confirmation.action === 'policy') await setPolicy(project, classification)
        else if (confirmation.action === 'approve') await approveProposal(project, confirmation.proposal)
        else await executeProposal(project, confirmation.proposal)
        if (!live.current) return
        setNotice(confirmation.action === 'execute' ? 'Execution submitted. Review operation state and runtime readiness.' : 'Saved. Review the updated server state.')
      })}>{confirmation?.action === 'policy' ? 'Save classification' : confirmation?.action === 'approve' ? 'Approve diff' : 'Execute rollback'}</Button></div>
    </DialogContent></Dialog>
  </section>
}

function Pagination({ before, next, onChange, label }: { before?: string; next: string | null; onChange: (value: string | undefined) => void; label: string }) {
  return <nav className="flex gap-2" aria-label={`${label} pagination`}><Button variant="outline" disabled={!before} onClick={() => onChange(undefined)}>Latest {label}</Button><Button variant="outline" disabled={!next} onClick={() => onChange(next ?? undefined)}>Older {label}</Button></nav>
}
function RunResult({ run }: { run: Run }) {
  return <div className="space-y-4"><h2 className="text-xl font-semibold">{kinds[run.kind]} · {run.state}</h2><p>Run: {run.run_id} · revision: {run.base_revision ?? 'unbound historical run'}</p>
    <p>Model: {run.model ?? 'unavailable'} · tools: {run.tool_calls} · estimated cost: ${run.estimated_cost_usd.toFixed(6)}</p><p>Created: {run.created_at} · completed: {run.completed_at ?? 'not completed'}</p>
    {run.result && <><p>{run.result.summary}</p>{run.result.insufficient_evidence && <p role="status">Insufficient evidence: this result does not establish a diagnosis.</p>}
      {(['observations', 'hypotheses'] as const).map((kind) => <div key={kind}><h3 className="font-semibold capitalize">{kind === 'hypotheses' ? 'Tentative hypotheses' : kind}</h3><ul className="list-disc space-y-2 pl-5">{run.result?.[kind]?.map((item, i) => <li key={i}>{item.statement} <span>{item.source_ids.map((id) => <a key={id} className="mr-2 underline" href={`#evidence-${run.run_id}-${id}`}>{id}</a>)}</span></li>)}</ul></div>)}
      <div><h3 className="font-semibold">Evidence gaps</h3><ul className="list-disc pl-5">{run.result.gaps.map((gap, i) => <li key={i}>{gap}</li>)}</ul></div></>}
    <div><h3 className="font-semibold">Evidence sources</h3><ul className="space-y-2">{run.evidence.map((e) => <li key={e.id} id={`evidence-${run.run_id}-${e.id}`} tabIndex={-1}>{e.id}: {e.tool} · {e.source} · {e.state} · {e.at}</li>)}</ul></div></div>
}
function ProposalReview({ proposal: p }: { proposal: Proposal }) {
  return <div className="space-y-2 text-sm"><p>Project: {p.project} · action: {p.diff.action} · state: {p.state}</p><p>Revision {p.base_revision} → retained revision {p.target_revision}</p><p>Changed paths: {p.diff.changed_paths.join(', ') || 'none'}</p><p className="break-all">Diff SHA-256: {p.diff_sha256}</p><p>Approval expires: {p.expires_at ?? 'not approved'}</p><p>Rollback plan: {p.rollback_plan}</p></div>
}

function MetricObservation({ metrics: m }: { metrics: NonNullable<NonNullable<Proposal['observation']>['metrics']> }) {
  const value = (n: number | null | undefined, unit: string) => n == null ? 'unavailable' : `${n.toFixed(4)} ${unit}`
  return <div className="space-y-2"><p>Collection: {m.state}{m.reason ? ` (${m.reason})` : ''} · component: {m.component ?? 'unavailable'}</p>
    <p>Observed: {m.observed_at ?? 'unavailable'} · window: {m.window_seconds ?? 'unknown'} seconds</p>
    <dl className="grid grid-cols-2 gap-2"><dt>Request rate</dt><dd>{value(m.request_rate_per_second, 'requests/s')}</dd><dt>Server error rate</dt><dd>{value(m.server_error_rate_per_second, 'errors/s')}</dd><dt>Mean request duration</dt><dd>{value(m.mean_request_duration_seconds, 'seconds')}</dd></dl><p>Missing values are unavailable, not zero.</p></div>
}
