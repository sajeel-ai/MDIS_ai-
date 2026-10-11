import { AlertCircle, CheckCircle2, Clock3, FileCheck2, LoaderCircle, UploadCloud, XCircle } from "lucide-react"
import { lifecycleStatusLabel, type LifecycleStatus } from "../../domain/documentLifecycle"

const styles: Record<LifecycleStatus, { className: string; Icon: typeof CheckCircle2 }> = {
  uploaded: { className: "border-slate-200 bg-slate-50 text-slate-700", Icon: UploadCloud },
  processing: { className: "border-blue-200 bg-blue-50 text-blue-700", Icon: LoaderCircle },
  failed: { className: "border-red-200 bg-red-50 text-red-700", Icon: AlertCircle },
  extracted: { className: "border-sky-200 bg-sky-50 text-sky-700", Icon: FileCheck2 },
  in_review: { className: "border-amber-200 bg-amber-50 text-amber-700", Icon: Clock3 },
  approved: { className: "border-emerald-200 bg-emerald-50 text-emerald-700", Icon: CheckCircle2 },
  rejected: { className: "border-rose-200 bg-rose-50 text-rose-700", Icon: XCircle },
}

export function StatusBadge({ status, className = "" }: { status: LifecycleStatus; className?: string }) {
  const style = styles[status]
  const Icon = style.Icon
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-medium ${style.className} ${className}`}>
      <Icon size={12} aria-hidden="true" className={status === "processing" ? "animate-spin" : undefined} />
      <span>{lifecycleStatusLabel[status]}</span>
    </span>
  )
}
