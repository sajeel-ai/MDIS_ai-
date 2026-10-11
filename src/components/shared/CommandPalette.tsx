import { useEffect, useMemo, useState } from "react"
import {
  ArrowRight,
  CheckSquare,
  FileText,
  GitBranch,
  Search,
  User,
} from "lucide-react"
import { fetchGlobalSearch, type GlobalSearchItem } from "../../services/api"
import { StatusBadge } from "./StatusBadge"

export interface CommandPaletteProps {
  isOpen: boolean
  onClose: () => void
  onNavigate: (view: string, documentId?: string) => void
}

const quickCommands = [
  { label: "Open Clinical Workspace", icon: FileText, view: "clinical" },
  { label: "Open Review Center Queue", icon: CheckSquare, view: "review" },
  { label: "View AI Operations & Telemetry", icon: GitBranch, view: "aiops" },
]

function resultDestination(
  item: GlobalSearchItem,
): [string, string | undefined] {
  if (item.type === "patient") return ["timeline", undefined]
  if (item.type === "finding") return ["review", undefined]
  if (
    item.status === "failed" ||
    item.status === "processing" ||
    item.status === "uploaded"
  )
    return ["documents", undefined]
  if (item.status === "approved") return ["approved-files", undefined]
  if (item.status === "in_review" || item.status === "rejected")
    return ["review", undefined]
  return ["clinical", item.id]
}

export function CommandPalette({
  isOpen,
  onClose,
  onNavigate,
}: CommandPaletteProps) {
  const [query, setQuery] = useState("")
  const [results, setResults] = useState<GlobalSearchItem[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [activeIndex, setActiveIndex] = useState(0)

  useEffect(() => {
    if (!isOpen) return
    setQuery("")
    setResults([])
    setError(null)
    setActiveIndex(0)
  }, [isOpen])

  useEffect(() => {
    if (!isOpen || query.trim().length < 3) {
      setResults([])
      setLoading(false)
      return
    }
    const timer = window.setTimeout(() => {
      setLoading(true)
      setError(null)
      void fetchGlobalSearch(query.trim())
        .then((data) => {
          setResults([...data.documents, ...data.patients, ...data.findings])
          setActiveIndex(0)
        })
        .catch(() => setError("Unable to search clinical records."))
        .finally(() => setLoading(false))
    }, 300)
    return () => window.clearTimeout(timer)
  }, [isOpen, query])

  const grouped = useMemo(
    () => ({
      Documents: results.filter((item) => item.type === "document"),
      Patients: results.filter((item) => item.type === "patient"),
      Findings: results.filter((item) => item.type === "finding"),
    }),
    [results],
  )
  const selectable = query.trim().length >= 3 ? results : quickCommands

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose()
      if (!isOpen) return
      if (event.key === "ArrowDown") {
        event.preventDefault()
        setActiveIndex((value) =>
          Math.min(value + 1, Math.max(0, selectable.length - 1)),
        )
      }
      if (event.key === "ArrowUp") {
        event.preventDefault()
        setActiveIndex((value) => Math.max(0, value - 1))
      }
      if (event.key === "Enter" && selectable.length > 0) {
        event.preventDefault()
        const item = selectable[activeIndex]
        if ("type" in item) {
          const [view, id] = resultDestination(item)
          onNavigate(view, id)
        } else {
          onNavigate(item.view)
        }
        onClose()
      }
    }
    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [activeIndex, isOpen, onClose, onNavigate, selectable])

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto overscroll-contain bg-black/40 p-4 pt-20 backdrop-blur-xs">
      <div className="flex min-h-0 w-full max-w-xl flex-col overflow-hidden rounded-lg border border-[#DCE7F3] bg-white shadow-2xl">
        <div className="flex items-center gap-3 border-b border-[#DCE7F3] px-4 py-3">
          <Search size={18} className="text-[#52627A]" aria-hidden="true" />
          <input
            type="search"
            autoFocus
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search documents, patients, findings (3+ characters)…"
            aria-label="Search documents, patients, and findings"
            className="w-full text-sm text-[#071A3D] outline-none placeholder:text-[#52627A]"
          />
          <kbd className="rounded border border-[#DCE7F3] bg-[#F5FAFF] px-1.5 py-0.5 text-[10px] text-[#52627A]">
            ESC
          </kbd>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-2">
          {query.trim().length < 3 ? (
            <section aria-label="Quick navigation">
              {quickCommands.map((item, index) => {
                const Icon = item.icon
                return (
                  <button
                    key={item.view}
                    type="button"
                    onClick={() => {
                      onNavigate(item.view)
                      onClose()
                    }}
                    className={
                      "group flex w-full items-center justify-between rounded-md px-3 py-2.5 text-left text-xs transition-colors hover:bg-[#EAF5FF] " +
                      (activeIndex === index ? "bg-[#EAF5FF]" : "")
                    }
                  >
                    <span className="flex items-center gap-3">
                      <Icon
                        size={14}
                        className="text-[#52627A] group-hover:text-[#146EF5]"
                      />
                      {item.label}
                    </span>
                    <ArrowRight size={12} className="text-[#52627A]" />
                  </button>
                )
              })}
            </section>
          ) : loading ? (
            <div className="p-6 text-center text-xs text-[#52627A]">
              Searching…
            </div>
          ) : error ? (
            <div
              role="alert"
              className="p-6 text-center text-xs text-[#B91C1C]"
            >
              {error}
            </div>
          ) : results.length === 0 ? (
            <div className="p-6 text-center text-xs text-[#52627A]">
              No results found.
            </div>
          ) : (
            Object.entries(grouped).map(
              ([label, items]) =>
                items.length > 0 && (
                  <section
                    key={label}
                    aria-labelledby={"search-group-" + label}
                    className="mb-2"
                  >
                    <h2
                      id={"search-group-" + label}
                      className="px-3 py-2 font-mono text-[10px] uppercase tracking-wider text-[#52627A]"
                    >
                      {label}
                    </h2>
                    {items.map((item) => {
                      const resultIndex = results.indexOf(item)
                      const Icon = item.type === "patient" ? User : FileText
                      return (
                        <button
                          key={item.type + "-" + item.id}
                          type="button"
                          onClick={() => {
                            const [view, id] = resultDestination(item)
                            onNavigate(view, id)
                            onClose()
                          }}
                          className={
                            "flex w-full items-center justify-between rounded-md px-3 py-2.5 text-left text-xs transition-colors hover:bg-[#EAF5FF] " +
                            (activeIndex === resultIndex ? "bg-[#EAF5FF]" : "")
                          }
                        >
                          <span className="flex min-w-0 items-center gap-3">
                            <Icon
                              size={14}
                              className="shrink-0 text-[#146EF5]"
                            />
                            <span className="truncate font-medium text-[#071A3D]">
                              {item.display_label}
                            </span>
                          </span>
                          <span className="ml-3 flex shrink-0 items-center gap-2">
                            <StatusBadge status={item.status} />
                            <ArrowRight size={12} className="text-[#52627A]" />
                          </span>
                        </button>
                      )
                    })}
                  </section>
                ),
            )
          )}
        </div>
        <div className="flex items-center justify-between border-t border-[#DCE7F3] bg-[#EAF5FF] px-4 py-2 text-[11px] text-[#52627A]">
          <span>↑ ↓ to navigate</span>
          <span>Enter to open · Esc to close</span>
        </div>
      </div>
    </div>
  )
}
