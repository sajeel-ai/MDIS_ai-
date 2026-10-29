import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { MutableRefObject } from 'react'
import { AlertTriangle, ChevronLeft, ChevronRight, CircleHelp, FileText, Flag, LoaderCircle, Minus, Plus } from 'lucide-react'
import {
  ApiError,
  addMissingReviewEntity,
  commentOnReviewEntity,
  editReviewEntity,
  fetchDocumentDetails,
  fetchDocumentEntities,
  fetchDocumentPageImage,
  fetchReviewPolicy,
  fetchReviewQueue,
  fetchReviewTaskDetail,
  rejectReviewEntity,
  safeApiErrorMessage,
  submitReviewDecision,
  undoReviewEntity,
  type ClinicalEntityItem,
  type DocumentDetailResponse,
  type ReviewEntityGroup,
  type ReviewPolicy,
  type ReviewTask,
  type ValidationReviewSummary,
} from '../../services/api'

const GROUPS: Array<{ id: ReviewEntityGroup; label: string; tone: string }> = [
  { id: 'confirmed-active', label: 'Confirmed active', tone: 'border-emerald-300 bg-emerald-50 text-emerald-900' },
  { id: 'historical-resolved', label: 'Historical / resolved', tone: 'border-slate-300 bg-slate-100 text-slate-800' },
  { id: 'family', label: 'Family history', tone: 'border-blue-300 bg-blue-50 text-blue-900' },
  { id: 'denied-ruled-out', label: 'Denied / ruled out', tone: 'border-slate-300 bg-slate-50 text-slate-700' },
  { id: 'uncertain-review', label: 'Uncertain / needs review', tone: 'border-amber-300 bg-amber-50 text-amber-950' },
  { id: 'instructions-conditional', label: 'Instructions / conditional', tone: 'border-cyan-300 bg-cyan-50 text-cyan-950' },
]

type Panel = 'document' | 'findings' | 'flags'
type Props = { initialTaskId?: string | null }

function isEditable(target: EventTarget | null): boolean {
  return target instanceof HTMLElement && (target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName))
}

function confidenceLabel(value: number | null | undefined, policy: ReviewPolicy | null) {
  if (value == null || !policy || !Number.isFinite(policy.high_priority_threshold) || !Number.isFinite(policy.confidence_threshold)) return { label: 'not available', reason: value == null ? 'No measured confidence was returned.' : 'Review thresholds are not available.' }
  if (value < policy.high_priority_threshold) return { label: 'Low', reason: `Below the configured high priority threshold (${policy.high_priority_threshold.toFixed(2)}).` }
  if (value < policy.confidence_threshold) return { label: 'Medium', reason: `Below the configured review threshold (${policy.confidence_threshold.toFixed(2)}).` }
  return { label: 'High', reason: `Meets the configured review threshold (${policy.confidence_threshold.toFixed(2)}).` }
}

function taskFlags(task: ReviewTask | null): ValidationReviewSummary[] {
  if (!task) return []
  if (task.validation_results?.length) return task.validation_results
  return task.validation ? [task.validation] : []
}

function sourceLabel(source?: ClinicalEntityItem['source']) {
  if (source === 'reviewer_edited') return 'Reviewer edited'
  if (source === 'reviewer_added') return 'Reviewer added'
  if (source === 'ai_extracted') return 'AI extracted'
  return 'not available'
}

function VirtualFindings({
  entities,
  selectedId,
  onSelect,
  policy,
  cardRefs,
}: {
  entities: ClinicalEntityItem[]
  selectedId: string | null
  onSelect: (entity: ClinicalEntityItem) => void
  policy: ReviewPolicy | null
  cardRefs: MutableRefObject<Record<string, HTMLButtonElement | null>>
}) {
  const [start, setStart] = useState(0)
  const viewport = useRef<HTMLDivElement>(null)
  const rowHeight = 164
  const visibleCount = 5
  const first = Math.min(start, Math.max(0, entities.length - visibleCount))
  const visible = entities.slice(first, first + visibleCount)
  useEffect(() => {
    const index = entities.findIndex((entity) => entity.id === selectedId)
    if (index >= 0 && viewport.current && (index < first || index >= first + visibleCount)) {
      viewport.current.scrollTop = index * rowHeight
    }
  }, [entities, selectedId, first])
  return (
    <div ref={viewport} onScroll={(event) => setStart(Math.floor(event.currentTarget.scrollTop / rowHeight))} className="min-h-0 flex-1 overflow-y-auto overscroll-contain" aria-label="Findings list">
      <div style={{ height: first * rowHeight }} aria-hidden="true" />
      {visible.map((item) => {
        const evidence = item.evidence_spans?.[0]
        const conf = item.extraction_confidence !== undefined ? item.extraction_confidence : item.confidence
        return (
          <button
            key={item.id}
            ref={(node) => { cardRefs.current[item.id] = node }}
            type="button"
            aria-pressed={selectedId === item.id}
            onClick={() => onSelect(item)}
            data-testid={`entity-card-${item.id}`}
            className={`mb-2 h-[156px] w-full overflow-hidden rounded-xl border p-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 ${selectedId === item.id ? 'border-blue-500 bg-blue-50' : 'border-slate-200 bg-white hover:border-blue-300'}`}
          >
            <div className="flex items-start justify-between gap-2">
              <span className="text-sm font-semibold text-slate-900">{item.normalized_value || item.raw_text}</span>
              <span className="shrink-0 rounded border border-slate-200 bg-slate-50 px-2 py-0.5 text-[11px] text-slate-700">{sourceLabel(item.source)}</span>
            </div>
            <p className="mt-1 truncate text-xs text-slate-600">{item.entity_type} · {item.section || 'not available'} · {item.assertion || 'not available'}</p>
            <p className="mt-2 line-clamp-2 text-xs text-slate-700">Evidence: {evidence?.exact_text || 'not available'}</p>
            <p className="mt-1 text-[11px] text-slate-600">Temporality: {item.temporality || 'not available'} · Experiencer: {item.experiencer || 'not available'}</p>
            <p className="mt-1 truncate text-[11px] text-slate-600" title={confidenceLabel(conf, policy).reason}>Confidence: {confidenceLabel(conf, policy).label}{conf == null ? '' : ` (${Math.round(Number(conf) * 100)}%)`} — {confidenceLabel(conf, policy).reason}</p>
          </button>
        )
      })}
      <div style={{ height: Math.max(0, entities.length - first - visible.length) * rowHeight }} aria-hidden="true" />
    </div>
  )
}

export function ReviewWorkspace({ initialTaskId }: Props) {
  const [task, setTask] = useState<ReviewTask | null>(null)
  const [queue, setQueue] = useState<ReviewTask[]>([])
  const [entities, setEntities] = useState<ClinicalEntityItem[]>([])
  const [document, setDocument] = useState<DocumentDetailResponse | null>(null)
  const [policy, setPolicy] = useState<ReviewPolicy | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [selectedGroup, setSelectedGroup] = useState<ReviewEntityGroup | null>(null)
  const [panel, setPanel] = useState<Panel>('document')
  const [page, setPage] = useState(1)
  const [imageRetry, setImageRetry] = useState(0)
  const [zoom, setZoom] = useState(100)
  const [imageUrl, setImageUrl] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [imageLoading, setImageLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [editMode, setEditMode] = useState(false)
  const [proposal, setProposal] = useState('')
  const [comment, setComment] = useState('')
  const [overrideReason, setOverrideReason] = useState('')
  const [acknowledged, setAcknowledged] = useState(false)
  const [conflict, setConflict] = useState(false)
  const [shortcuts, setShortcuts] = useState(false)
  const [addMode, setAddMode] = useState(false)
  const [drawStart, setDrawStart] = useState<[number, number] | null>(null)
  const [drawnBox, setDrawnBox] = useState<[number, number, number, number] | null>(null)
  const [addType, setAddType] = useState('symptom')
  const [addText, setAddText] = useState('')
  const [addEvidenceText, setAddEvidenceText] = useState('')
  const cardRefs = useRef<Record<string, HTMLButtonElement | null>>({})

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      let taskId = initialTaskId || undefined
      let initial: ReviewTask | undefined
      if (taskId) initial = await fetchReviewTaskDetail(taskId)
      else {
        const result = await fetchReviewQueue(1, 100, undefined, 'pending')
        setQueue(result.items)
        initial = result.items[0] ? await fetchReviewTaskDetail(result.items[0].id) : undefined
        taskId = initial?.id
      }
      if (!initial || !taskId) {
        setTask(null)
        setEntities([])
        setDocument(null)
        return
      }
      setTask(initial)
      const [entityResult, documentResult, policyResult, queueResult] = await Promise.all([
        fetchDocumentEntities(initial.document_id),
        fetchDocumentDetails(initial.document_id),
        fetchReviewPolicy().catch(() => null),
        fetchReviewQueue(1, 100, undefined, 'all', undefined, initial.document_id).catch(() => ({ items: [], total: 0, page: 1, page_size: 100, has_next: false })),
      ])
      setEntities(entityResult)
      setDocument(documentResult)
      setPolicy(policyResult)
      setQueue(queueResult.items)
      const nextSelected = initial.entity?.id || entityResult[0]?.id || null
      setSelectedId(nextSelected)
      setSelectedGroup(entityResult.find((item) => item.id === nextSelected)?.group || null)
      setPage(1)
      setProposal(initial.entity?.normalized_value || initial.entity?.raw_text || '')
    } catch (caught) {
      setError(safeApiErrorMessage(caught, 'Unable to load this review task.'))
    } finally {
      setLoading(false)
    }
  }, [initialTaskId])

  useEffect(() => { void load() }, [load])

  useEffect(() => {
    if (!task?.document_id) return
    let active = true
    setImageLoading(true)
    fetchDocumentPageImage(task.document_id, page)
      .then((blob) => {
        if (!active) return
        setError(null)
        const nextUrl = URL.createObjectURL(blob)
        setImageUrl((oldUrl) => {
          if (oldUrl) URL.revokeObjectURL(oldUrl)
          return nextUrl
        })
      })
      .catch((caught) => {
        if (active) setError(safeApiErrorMessage(caught, 'Page image is unavailable.'))
      })
      .finally(() => { if (active) setImageLoading(false) })
    return () => { active = false }
  }, [task?.document_id, page, imageRetry])

  useEffect(() => () => { if (imageUrl) URL.revokeObjectURL(imageUrl) }, [imageUrl])

  const selected = entities.find((entity) => entity.id === selectedId) || null
  const currentTask = queue.find((item) => item.entity_id === selectedId) || task
  const groups = useMemo(() => Object.fromEntries(GROUPS.map((group) => [group.id, entities.filter((entity) => entity.group === group.id)])) as Record<ReviewEntityGroup, ClinicalEntityItem[]>, [entities])
  const groupedItems = selectedGroup ? groups[selectedGroup] : entities.filter((entity) => !entity.group)
  const flags = taskFlags(currentTask)
  const unacknowledgedCritical = flags.some((flag) => flag.severity?.toLowerCase() === 'critical' || /critical|conflict/i.test(flag.rule_code || ''))
  const hasPatient = Boolean(currentTask?.patient?.id)
  const acceptDisabledReason = currentTask?.patient_deleted
    ? 'Cannot accept: the linked patient is soft-deleted. Restore the patient first.'
    : !hasPatient
    ? 'Cannot accept: this document has no linked patient.'
    : unacknowledgedCritical && !acknowledged
      ? 'Cannot accept: acknowledge the critical or conflict flag first.'
      : flags.length > 0 && !overrideReason.trim()
        ? 'A written reason is required before overriding a returned safety flag.'
        : null
  const flaggedEntityIds = [...new Set(queue.filter((item) => taskFlags(item).length > 0 && item.entity_id).map((item) => item.entity_id as string))]
  const activeFlagIndex = selectedId ? flaggedEntityIds.indexOf(selectedId) : -1

  useEffect(() => {
    if (selectedId) cardRefs.current[selectedId]?.focus()
  }, [selectedId, selectedGroup])

  const selectEntity = (entity: ClinicalEntityItem) => {
    setSelectedId(entity.id)
    setSelectedGroup(entity.group || null)
    const evidencePage = entity.evidence_spans?.find((span) => span.bbox)?.page_number
    if (evidencePage) setPage(evidencePage)
    setProposal(entity.normalized_value || entity.raw_text)
    setEditMode(false)
    cardRefs.current[entity.id]?.focus()
    setPanel('findings')
  }

  const refresh = async () => {
    await load()
    setSaved(true)
    window.setTimeout(() => setSaved(false), 2500)
  }

  const onAccept = async () => {
    if (!selected || !currentTask || acceptDisabledReason) return
    setSaving(true)
    setError(null)
    try {
      await submitReviewDecision(currentTask.id, {
        decision: 'approved', expected_version: currentTask.version ?? undefined,
        acknowledged, justification: overrideReason.trim() || undefined, comment: comment.trim() || undefined,
      })
      setEditMode(false)
      await refresh()
    } catch (caught) { handleActionError(caught) } finally { setSaving(false) }
  }

  const onEdit = async () => {
    if (!selected) return
    setSaving(true)
    setError(null)
    try {
      await editReviewEntity(selected.id, { expected_version: selected.version ?? 1, normalized_value: proposal.trim() })
      setEditMode(false)
      await refresh()
    } catch (caught) { handleActionError(caught) } finally { setSaving(false) }
  }

  const onReject = async () => {
    if (!selected) return
    setSaving(true)
    setError(null)
    try {
      await rejectReviewEntity(selected.id, selected.version ?? 1)
      await refresh()
    } catch (caught) { handleActionError(caught) } finally { setSaving(false) }
  }

  const onComment = async () => {
    if (!selected || !comment.trim()) return
    setSaving(true)
    setError(null)
    try {
      await commentOnReviewEntity(selected.id, selected.version ?? 1, comment.trim())
      setComment('')
      await refresh()
    } catch (caught) { handleActionError(caught) } finally { setSaving(false) }
  }

  const onUndo = async () => {
    if (!selected) return
    setSaving(true)
    setError(null)
    try {
      await undoReviewEntity(selected.id, selected.version ?? 1)
      await refresh()
    } catch (caught) { handleActionError(caught) } finally { setSaving(false) }
  }

  const onAddMissing = async () => {
    if (!task || !document || !drawnBox || !addType.trim() || !addText.trim() || !addEvidenceText.trim()) return
    setSaving(true)
    setError(null)
    try {
      await addMissingReviewEntity(task.document_id, {
        expected_version: document.version_number,
        type: addType.trim(), text: addText.trim(), page, bbox: drawnBox,
        evidence_text: addEvidenceText.trim(),
      })
      setAddMode(false); setDrawnBox(null); setAddText(''); setAddEvidenceText('')
      await refresh()
    } catch (caught) { handleActionError(caught) } finally { setSaving(false) }
  }

  function handleActionError(caught: unknown) {
    if (caught instanceof ApiError && caught.status === 409) setConflict(true)
    setError(caught instanceof ApiError && caught.status === 409
      ? 'This item changed since it was loaded. Reload before continuing.'
      : safeApiErrorMessage(caught, 'Unable to save this review action.'))
  }

  const stepFlag = (direction: -1 | 1) => {
    if (!flaggedEntityIds.length) return
    const nextIndex = activeFlagIndex < 0 ? 0 : (activeFlagIndex + direction + flaggedEntityIds.length) % flaggedEntityIds.length
    const next = entities.find((entity) => entity.id === flaggedEntityIds[nextIndex])
    if (next) selectEntity(next)
  }

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (isEditable(event.target)) return
      if (event.key === '?') { event.preventDefault(); setShortcuts((open) => !open); return }
      if (event.key === 'ArrowDown') { event.preventDefault(); stepFlag(1) }
      if (event.key === 'ArrowUp') { event.preventDefault(); stepFlag(-1) }
      if (event.key === 'Escape') { setShortcuts(false); if (editMode) { setEditMode(false); setProposal(selected?.normalized_value || selected?.raw_text || '') } }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [activeFlagIndex, entities, flaggedEntityIds.length, editMode, selected])

  if (loading) return <div className="grid h-[calc(100dvh-8rem)] grid-cols-1 gap-3 p-4 md:grid-cols-3" aria-label="Loading review workspace"><div className="animate-pulse rounded-xl bg-slate-100" /><div className="animate-pulse rounded-xl bg-slate-100" /><div className="animate-pulse rounded-xl bg-slate-100" /></div>
  if (error && !task) return <div className="m-5 rounded-xl border border-rose-200 bg-rose-50 p-5 text-sm text-rose-900" role="alert">{error}<button className="ml-3 underline" onClick={() => void load()}>Retry</button></div>
  if (!task) return <div className="m-5 rounded-xl border border-slate-200 bg-white p-8 text-center text-slate-700">No review tasks are available.</div>

  return (
    <main className="flex h-[calc(100dvh-7rem)] min-h-[560px] min-w-0 flex-col overflow-hidden bg-slate-50 text-slate-900" aria-label="Review workspace">
      <header className="flex shrink-0 items-center justify-between gap-3 border-b border-slate-200 bg-white px-4 py-3">
        <div className="min-w-0"><h1 className="truncate text-base font-semibold">Review workspace</h1><p className="truncate text-xs text-slate-600">{task.document?.file_name || 'Document'} · Decision by: {task.decision_actor || 'not available'} · {task.decision_at ? new Date(task.decision_at).toLocaleString() : 'time not available'}</p></div>
        <div className="flex shrink-0 items-center gap-2"><span role="status" className="text-xs text-emerald-800">{saving ? 'Saving…' : saved ? 'Saved' : ''}</span><button aria-label="Keyboard shortcuts" title="Keyboard shortcuts (?)" onClick={() => setShortcuts(true)} className="rounded-lg border border-slate-300 p-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600"><CircleHelp size={17} /></button></div>
      </header>

      <nav role="tablist" aria-label="Review panels" className="flex shrink-0 border-b border-slate-200 bg-white md:hidden">
        {(['document', 'findings', 'flags'] as Panel[]).map((item) => <button key={item} role="tab" aria-selected={panel === item} onClick={() => setPanel(item)} className={`flex-1 px-3 py-3 text-sm capitalize focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-blue-600 ${panel === item ? 'border-b-2 border-blue-600 font-semibold text-blue-900' : 'text-slate-600'}`}>{item === 'findings' ? 'Findings' : item[0].toUpperCase() + item.slice(1)}</button>)}
      </nav>

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 overflow-hidden p-3 md:grid-cols-[minmax(0,1.15fr)_minmax(320px,1fr)_minmax(240px,0.75fr)]">
        <section aria-label="Document" className={`${panel === 'document' ? 'flex' : 'hidden'} min-h-0 min-w-0 flex-col overflow-hidden rounded-xl border border-slate-200 bg-white md:flex`}>
          <div className="flex items-center justify-between gap-2 border-b border-slate-200 px-3 py-2"><h2 className="flex items-center gap-2 text-sm font-semibold"><FileText size={16} />Document</h2><div className="flex items-center gap-1"><button aria-label="Previous page" disabled={page <= 1} onClick={() => setPage((value) => value - 1)} className="rounded p-1.5 hover:bg-slate-100 disabled:opacity-40"><ChevronLeft size={16} /></button><span className="min-w-16 text-center text-xs">Page {page} / {document?.page_count ?? 'not available'}</span><button aria-label="Next page" disabled={page >= (document?.page_count || 1)} onClick={() => setPage((value) => value + 1)} className="rounded p-1.5 hover:bg-slate-100 disabled:opacity-40"><ChevronRight size={16} /></button><button aria-label="Zoom out" onClick={() => setZoom((value) => Math.max(50, value - 10))} className="rounded p-1.5 hover:bg-slate-100"><Minus size={16} /></button><span className="w-10 text-center text-xs">{zoom}%</span><button aria-label="Zoom in" onClick={() => setZoom((value) => Math.min(200, value + 10))} className="rounded p-1.5 hover:bg-slate-100"><Plus size={16} /></button></div></div>
          <div className="min-h-0 flex-1 overflow-auto overscroll-contain bg-slate-100 p-3" data-testid="page-scroll-container">
            {imageLoading && <div className="flex h-full items-center justify-center text-sm text-slate-600"><LoaderCircle className="mr-2 animate-spin" size={18} />Loading page…</div>}
            {!imageLoading && imageUrl && <div className="relative mx-auto" style={{ width: `${zoom}%`, maxWidth: 'none' }}><img src={imageUrl} alt={`Original document page ${page}`} className="block h-auto w-full select-none" draggable={false} />{entities.map((item) => { const box = item.evidence_spans?.find((span) => span.page_number === page)?.bbox; if (!box) return null; const [x1, y1, x2, y2] = box; return <button key={item.id} type="button" data-testid={`source-box-${item.id}`} aria-label={`Evidence highlight for ${item.normalized_value || item.raw_text}`} aria-pressed={selectedId === item.id} onClick={() => selectEntity(item)} className={`absolute border-2 ${selectedId === item.id ? 'border-amber-600 bg-amber-300/30' : 'border-cyan-600 bg-cyan-300/20'} focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-700`} style={{ left: `${x1 * 100}%`, top: `${y1 * 100}%`, width: `${Math.max(0, x2 - x1) * 100}%`, height: `${Math.max(0, y2 - y1) * 100}%` }} />})}{addMode && <div className="absolute inset-0 z-10 cursor-crosshair touch-none" aria-label="Draw evidence box" onPointerDown={(event) => { const rect = event.currentTarget.getBoundingClientRect(); const x = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)); const y = Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height)); setDrawStart([x, y]); setDrawnBox(null) }} onPointerUp={(event) => { if (!drawStart) return; const rect = event.currentTarget.getBoundingClientRect(); const x = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)); const y = Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height)); setDrawnBox([Math.min(x, drawStart[0]), Math.min(y, drawStart[1]), Math.max(x, drawStart[0]), Math.max(y, drawStart[1])]); setDrawStart(null) }}>{drawnBox && <div className="absolute border-2 border-amber-600 bg-amber-300/30" style={{ left: `${drawnBox[0] * 100}%`, top: `${drawnBox[1] * 100}%`, width: `${(drawnBox[2] - drawnBox[0]) * 100}%`, height: `${(drawnBox[3] - drawnBox[1]) * 100}%` }} />}</div>}</div>}
            {!imageLoading && !imageUrl && <div className="flex h-full items-center justify-center text-sm text-slate-600">Page image is unavailable. <button className="ml-1 underline" onClick={() => setImageRetry((value) => value + 1)}>Retry</button></div>}
          </div>
          {!selected?.evidence_spans?.some((span) => span.page_number === page && span.bbox) && <p className="border-t border-slate-200 bg-amber-50 px-3 py-2 text-xs text-amber-950">Evidence highlighting unavailable for this item.</p>}
          <div className="flex flex-wrap items-center gap-3 border-t border-slate-200 px-3 py-2 text-[11px] text-slate-700"><strong>Legend</strong><span><i className="mr-1 inline-block size-2 rounded-full bg-emerald-600" />Present / accepted</span><span><i className="mr-1 inline-block size-2 rounded-full bg-slate-500" />Absent / denied</span><span><i className="mr-1 inline-block size-2 rounded-full bg-blue-600" />Family</span><span><i className="mr-1 inline-block size-2 rounded-full bg-amber-600" />Uncertain / review</span><span><i className="mr-1 inline-block size-2 rounded-full bg-red-600" />Critical</span></div>
        </section>

        <section aria-label="Findings" className={`${panel === 'findings' ? 'flex' : 'hidden'} min-h-0 min-w-0 flex-col overflow-hidden rounded-xl border border-slate-200 bg-slate-50 md:flex`}>
          <div className="shrink-0 border-b border-slate-200 bg-white p-3"><div className="flex items-center justify-between"><h2 className="text-sm font-semibold">Findings</h2><div className="flex gap-1"><button aria-label="Previous flagged entity" onClick={() => stepFlag(-1)} className="rounded border border-slate-300 p-1.5"><ChevronLeft size={15} /></button><button aria-label="Next flagged entity" onClick={() => stepFlag(1)} className="rounded border border-slate-300 p-1.5"><ChevronRight size={15} /></button></div></div><div className="mt-2 flex flex-wrap gap-1">{GROUPS.map((group) => <button key={group.id} aria-pressed={selectedGroup === group.id} onClick={() => setSelectedGroup(group.id)} className={`rounded-full border px-2 py-1 text-[10px] ${group.tone} ${selectedGroup === group.id ? 'ring-2 ring-blue-600' : ''}`}>{group.label} ({groups[group.id].length})</button>)}</div></div>
          <div className="min-h-0 flex-1 p-2">
            {groupedItems.length ? <VirtualFindings entities={groupedItems} selectedId={selectedId} onSelect={selectEntity} policy={policy} cardRefs={cardRefs} /> : <div className="rounded-lg border border-slate-200 bg-white p-4 text-xs text-slate-600">{selectedGroup ? `No ${GROUPS.find((item) => item.id === selectedGroup)?.label.toLowerCase()} findings returned.` : 'Group not available for this legacy finding.'}</div>}
          </div>
          {selected && <div className="shrink-0 space-y-2 border-t border-slate-200 bg-white p-3">
            <div className="flex flex-wrap items-center gap-2"><span className="text-xs font-semibold">{selected.normalized_value || selected.raw_text}</span><span className="rounded bg-slate-100 px-2 py-0.5 text-[10px]">{sourceLabel(selected.source)}</span></div>
            {editMode ? <div className="space-y-2"><div data-testid="edit-diff" className="rounded border border-slate-200 bg-slate-50 p-2 text-xs"><div>Original AI value: <del>{selected.original_ai_value || selected.normalized_value || selected.raw_text}</del></div><div>Proposed change: <ins>{proposal || 'not available'}</ins></div></div><label className="block text-xs" htmlFor="proposed-value">Proposed value</label><input id="proposed-value" value={proposal} onChange={(event) => setProposal(event.target.value)} className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600" /><div className="flex gap-2"><button onClick={() => void onEdit()} disabled={saving || !proposal.trim()} className="rounded bg-blue-700 px-3 py-1.5 text-xs text-white disabled:opacity-50">{saving ? 'Saving…' : 'Save changes'}</button><button onClick={() => { setEditMode(false); setProposal(selected.normalized_value || selected.raw_text) }} className="rounded border border-slate-300 px-3 py-1.5 text-xs">Cancel</button></div></div> : <div className="flex flex-wrap gap-2"><button onClick={() => setEditMode(true)} disabled={saving} className="rounded border border-slate-300 px-3 py-1.5 text-xs">Edit</button><button onClick={() => void onReject()} disabled={saving} className="rounded border border-rose-300 px-3 py-1.5 text-xs text-rose-800">Reject</button><button onClick={() => void onUndo()} disabled={saving || currentTask?.status === 'approved'} className="rounded border border-slate-300 px-3 py-1.5 text-xs">Undo</button></div>}
            <label className="block text-xs" htmlFor="review-comment">Comment</label><div className="flex gap-2"><input id="review-comment" value={comment} onChange={(event) => setComment(event.target.value)} className="min-w-0 flex-1 rounded border border-slate-300 px-2 py-1.5 text-xs" /><button onClick={() => void onComment()} disabled={saving || !comment.trim()} className="rounded border border-slate-300 px-2 text-xs">Save comment</button></div>
            <div className="flex flex-wrap gap-2"><button onClick={() => void onAccept()} disabled={saving || Boolean(acceptDisabledReason)} className="rounded bg-emerald-700 px-3 py-1.5 text-xs font-medium text-white disabled:cursor-not-allowed disabled:opacity-50">Accept</button><button onClick={() => { setAddMode((enabled) => !enabled); setDrawnBox(null) }} disabled={saving || conflict} className="rounded border border-blue-300 px-3 py-1.5 text-xs text-blue-900">{addMode ? 'Cancel add' : 'Add missing item'}</button></div>
            {addMode && <div className="space-y-2 rounded border border-blue-200 bg-blue-50 p-2"><p className="text-xs">Draw a box on page {page}, then enter the finding and exact OCR evidence. Confidence will be not available; the item requires individual review.</p><label className="block text-xs">Type<input value={addType} onChange={(event) => setAddType(event.target.value)} className="mt-1 w-full rounded border p-1.5" /></label><label className="block text-xs">Text<input value={addText} onChange={(event) => setAddText(event.target.value)} className="mt-1 w-full rounded border p-1.5" /></label><label className="block text-xs">Evidence text<input value={addEvidenceText} onChange={(event) => setAddEvidenceText(event.target.value)} className="mt-1 w-full rounded border p-1.5" /></label><button onClick={() => void onAddMissing()} disabled={saving || !drawnBox || !addText.trim() || !addEvidenceText.trim()} className="rounded bg-blue-700 px-3 py-1.5 text-xs text-white disabled:opacity-50">{saving ? 'Saving…' : 'Save finding'}</button></div>}
            {acceptDisabledReason && <p role="status" className="rounded bg-amber-50 p-2 text-xs text-amber-950"><AlertTriangle size={13} className="mr-1 inline" />{acceptDisabledReason}</p>}
            {unacknowledgedCritical && <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={acknowledged} onChange={(event) => setAcknowledged(event.target.checked)} />Acknowledge critical or conflict flag</label>}
            {flags.length > 0 && <div><label htmlFor="override-reason" className="block text-xs">Written override reason (required)</label><textarea id="override-reason" value={overrideReason} onChange={(event) => setOverrideReason(event.target.value)} className="mt-1 w-full rounded border border-slate-300 p-2 text-xs" rows={2} /></div>}
          </div>}
        </section>

        <section aria-label="Flags" className={`${panel === 'flags' ? 'flex' : 'hidden'} min-h-0 min-w-0 flex-col overflow-hidden rounded-xl border border-slate-200 bg-white md:flex`}>
          <h2 className="shrink-0 border-b border-slate-200 p-3 text-sm font-semibold">Flags returned by the backend</h2>
          <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-3">{flags.length ? flags.map((flag, index) => <article key={`${flag.rule_code}-${index}`} className={`rounded-lg border p-3 ${flag.severity?.toLowerCase() === 'critical' ? 'border-red-300 bg-red-50 text-red-950' : 'border-amber-300 bg-amber-50 text-amber-950'}`}><div className="flex items-center gap-2 text-xs font-semibold"><Flag size={14} />{flag.severity || 'Severity not available'} · {flag.rule_code || 'Rule not available'}</div><p className="mt-1 text-xs">{flag.message || 'Message not available'}</p><button onClick={() => selected && selectEntity(selected)} className="mt-2 text-xs font-medium underline">Go to affected entity</button></article>) : <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs text-slate-600">No flags were returned for this review task.</div>}</div>
          <div className="shrink-0 border-t border-slate-200 bg-slate-50 p-3 text-[11px] text-slate-700">
            <p>Checks run: {task?.checks_ran?.length ? task.checks_ran.join(', ') : 'not available'}</p>
            <p className="mt-1">Not implemented: {task?.checks_not_implemented?.length ? task.checks_not_implemented.join(', ') : 'not available'}</p>
          </div>
        </section>
      </div>

      {error && <div role="alert" className="absolute bottom-16 left-1/2 z-20 -translate-x-1/2 rounded-lg border border-rose-300 bg-rose-50 px-4 py-3 text-sm text-rose-950 shadow">{error}{conflict && <button onClick={() => { setConflict(false); void load() }} className="ml-3 font-semibold underline">Reload</button>}</div>}
      {shortcuts && <div role="dialog" aria-modal="true" aria-label="Keyboard shortcuts" className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/30 p-4" onClick={() => setShortcuts(false)}><div className="w-full max-w-sm rounded-xl bg-white p-5 shadow-xl" onClick={(event) => event.stopPropagation()}><h2 className="text-base font-semibold">Keyboard shortcuts</h2><ul className="mt-3 space-y-2 text-sm"><li>↑ / ↓ — Previous or next flagged entity</li><li>? — Open or close this help</li><li>Esc — Cancel an unsaved edit</li></ul><button autoFocus onClick={() => setShortcuts(false)} className="mt-4 rounded bg-blue-700 px-3 py-2 text-sm text-white">Close</button></div></div>}
    </main>
  )
}
