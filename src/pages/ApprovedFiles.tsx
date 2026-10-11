import { useEffect, useState } from "react"
import { CheckCircle2, Download, ExternalLink, FileCheck2, RefreshCw, Send, ShieldCheck } from "lucide-react"
import { AppLayout } from "../layouts/AppLayout"
import {
  fetchDocumentFHIR,
  fetchDocuments,
  fetchFHIRMetadata,
  fetchReviewQueue,
  pushSyntheticFHIR,
  safeApiErrorMessage,
  type DocumentItem,
  type FHIRMetadataCheck,
} from "../services/api"

export interface ApprovedFilesPageProps {
  onNavigate: (view: string, documentId?: string, reviewTaskId?: string) => void
}

export function ApprovedFilesPage({ onNavigate }: ApprovedFilesPageProps) {
  const [documents, setDocuments] = useState<DocumentItem[]>([])
  const [total, setTotal] = useState(0)
  const [fhir, setFhir] = useState<FHIRMetadataCheck | null>(null)
  const [reviewTaskByDocument, setReviewTaskByDocument] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [feedback, setFeedback] = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await fetchDocuments(1, 100, "approved", undefined, false, "updated_desc")
      setDocuments(result.items || [])
      setTotal(result.total || 0)
      try {
        setFhir(await fetchFHIRMetadata())
      } catch {
        // FHIR connection status is restricted to admin/operator roles; the
        // approved document list remains available to other authorized roles.
        setFhir(null)
      }
      try {
        const reviewQueue = await fetchReviewQueue(1, 100, "all", "all", "")
        setReviewTaskByDocument(Object.fromEntries((reviewQueue.items || []).map((task) => [task.document_id, task.id])))
      } catch {
        setReviewTaskByDocument({})
      }
    } catch (err) {
      setError(safeApiErrorMessage(err, "Unable to load approved files."))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const download = async (file: DocumentItem) => {
    setBusyId(file.id)
    setFeedback(null)
    try {
      const bundle = await fetchDocumentFHIR(file.id)
      const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: "application/fhir+json" })
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement("a")
      anchor.href = url
      anchor.download = `${file.file_name || file.id}.fhir.json`
      anchor.click()
      URL.revokeObjectURL(url)
      setFeedback("FHIR export downloaded and recorded in the audit trail.")
    } catch (err) {
      setFeedback(safeApiErrorMessage(err, "FHIR export is unavailable."))
    } finally {
      setBusyId(null)
    }
  }

  const push = async (file: DocumentItem) => {
    setBusyId(file.id)
    setFeedback(null)
    try {
      await pushSyntheticFHIR(file.id)
      setFeedback("Synthetic document pushed to the configured FHIR test server.")
    } catch (err) {
      setFeedback(safeApiErrorMessage(err, "FHIR test push was not completed."))
    } finally {
      setBusyId(null)
    }
  }

  return (
    <AppLayout activeView="approved-files" onNavigate={onNavigate}>
      <div className="space-y-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <FileCheck2 size={20} className="text-[#146EF5]" aria-hidden="true" />
              <h1 className="text-xl font-bold text-[#071A3D]">Approved Files</h1>
            </div>
            <p className="mt-1 text-xs text-[#52627A]">Human-approved clinical documents and their FHIR export status.</p>
          </div>
          <button type="button" onClick={() => void load()} className="inline-flex items-center gap-2 rounded-md bg-[#146EF5] px-3 py-2 text-xs font-semibold text-white transition hover:bg-[#0E2A5C]">
            <RefreshCw size={14} aria-hidden="true" /> Refresh
          </button>
        </div>

        <div className="grid gap-3 sm:grid-cols-3">
          <div className="rounded-lg border border-[#DCE7F3] bg-white p-4"><div className="text-[10px] font-mono uppercase text-[#52627A]">Approved files</div><div className="mt-1 text-2xl font-bold text-[#071A3D]">{total}</div></div>
          <div className="rounded-lg border border-[#DCE7F3] bg-white p-4"><div className="text-[10px] font-mono uppercase text-[#52627A]">FHIR server</div><div className="mt-1 text-sm font-semibold text-[#071A3D]">{fhir?.reachable ? `Connected · ${fhir.fhir_version || "4.x"}` : fhir?.status === "not_configured" ? "Not configured" : "Unavailable"}</div></div>
          <div className="rounded-lg border border-[#DCE7F3] bg-white p-4"><div className="text-[10px] font-mono uppercase text-[#52627A]">Export policy</div><div className="mt-1 text-sm font-semibold text-[#071A3D]">Approved entities only</div></div>
        </div>

        {feedback && <div role="status" className="rounded-lg border border-[#DCE7F3] bg-[#EAF5FF] p-3 text-xs text-[#071A3D]">{feedback}</div>}
        {error && <div role="alert" className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-xs text-rose-800">{error}</div>}

        <section className="overflow-hidden rounded-lg border border-[#DCE7F3] bg-white">
          <div className="flex items-center gap-2 border-b border-[#DCE7F3] px-4 py-3 text-xs font-semibold text-[#071A3D]"><ShieldCheck size={15} className="text-emerald-600" aria-hidden="true" /> Approved clinical records</div>
          {loading ? <div className="p-10 text-center text-xs text-[#52627A]">Loading approved files…</div> : documents.length === 0 ? <div className="p-10 text-center text-xs text-[#52627A]">No approved files are available.</div> : <div className="divide-y divide-[#DCE7F3]">
            {documents.map((item) => {
              const busy = busyId === item.id
              return <article key={item.id} className="flex flex-col gap-4 p-4 transition-colors hover:bg-[#F5FAFF] lg:flex-row lg:items-center lg:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2"><CheckCircle2 size={15} className="text-emerald-600" aria-hidden="true" /><h2 className="truncate text-sm font-semibold text-[#071A3D]">{item.file_name || item.doc_type}</h2><span className="rounded bg-emerald-50 px-2 py-0.5 text-[10px] font-mono uppercase text-emerald-700">Approved</span></div>
                  <div className="mt-1 text-xs text-[#52627A]">{item.patient_name || "Patient not linked"}{item.mrn ? ` · MRN ${item.mrn}` : ""} · {item.doc_type}</div>
                  <div className="mt-1 text-[10px] font-mono text-[#8FA5CC]">Updated {new Date(item.last_updated).toLocaleString()}</div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button type="button" onClick={() => onNavigate("clinical", item.id)} className="inline-flex items-center gap-1.5 rounded-md border border-[#DCE7F3] px-3 py-2 text-xs font-semibold text-[#146EF5] transition hover:bg-[#EAF5FF]"><ExternalLink size={13} aria-hidden="true" /> Document</button>
                  <button type="button" onClick={() => onNavigate("review", undefined, reviewTaskByDocument[item.id])} className="rounded-md border border-[#DCE7F3] px-3 py-2 text-xs font-semibold text-[#146EF5] transition hover:bg-[#EAF5FF]">Review Center</button>
                  <button type="button" onClick={() => onNavigate("audit", item.id)} className="rounded-md border border-[#DCE7F3] px-3 py-2 text-xs font-semibold text-[#52627A] transition hover:bg-[#EAF5FF]">Audit trail</button>
                  <button type="button" disabled={busy} onClick={() => void download(item)} className="inline-flex items-center gap-1.5 rounded-md bg-[#146EF5] px-3 py-2 text-xs font-semibold text-white transition hover:bg-[#0E2A5C] disabled:opacity-50"><Download size={13} aria-hidden="true" /> FHIR JSON</button>
                  <button type="button" disabled={busy || !fhir?.reachable} title={!fhir?.reachable ? "Connect a FHIR R4 test server first" : undefined} onClick={() => void push(item)} className="inline-flex items-center gap-1.5 rounded-md bg-[#0E2A5C] px-3 py-2 text-xs font-semibold text-white transition hover:bg-[#071A3D] disabled:cursor-not-allowed disabled:opacity-50"><Send size={13} aria-hidden="true" /> Test push</button>
                </div>
              </article>
            })}
          </div>}
        </section>
      </div>
    </AppLayout>
  )
}
