import React, { useState, useEffect, useRef } from "react"

import { Search, Bell, Menu, HelpCircle } from "lucide-react"
import {
  fetchNotifications,
  fetchHealthStatus,
  safeApiErrorMessage,
  type NotificationItem,
  type SystemStatusCode,
} from "../../services/api"

import logoUrl from "../../public/Glossy Blue Ribbon M Emblem.png"

export interface HeaderProps {
  onOpenSearch: () => void

  onToggleMobileNav: () => void

  onNavigate: (view: string, documentId?: string, reviewTaskId?: string) => void
}

export function Header({
  onOpenSearch,
  onToggleMobileNav,
  onNavigate,
}: HeaderProps) {
  const [notifOpen, setNotifOpen] = useState(false)

  const [notifPosition, setNotifPosition] = useState({ top: 0, left: 0 })

  const [notificationTasks, setNotificationTasks] = useState<NotificationItem[]>([])

  const [notifCount, setNotifCount] = useState(0)

  const [notificationLoading, setNotificationLoading] = useState(false)

  const [notificationError, setNotificationError] = useState<string | null>(null)

  const [systemStatus, setSystemStatus] = useState<SystemStatusCode>("unknown")

  const headerRef = useRef<HTMLElement>(null)

  const mobileBellRef = useRef<HTMLButtonElement>(null)

  const desktopBellRef = useRef<HTMLButtonElement>(null)

  const notifPanelRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!notifOpen) return

    const updatePosition = () => {
      if (window.matchMedia("(min-width: 768px)").matches) {
        const button = desktopBellRef.current

        if (button) {
          const rect = button.getBoundingClientRect()

          setNotifPosition({ top: rect.bottom + 8, left: rect.right - 320 })
        }
      } else if (headerRef.current) {
        setNotifPosition((position) => ({
          ...position,

          top:
            headerRef.current?.getBoundingClientRect().bottom ?? position.top,
        }))
      }
    }

    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target as Node

      if (
        !notifPanelRef.current?.contains(target) &&
        !mobileBellRef.current?.contains(target) &&
        !desktopBellRef.current?.contains(target)
      )
        setNotifOpen(false)
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setNotifOpen(false)
    }

    updatePosition()

    document.addEventListener("pointerdown", handlePointerDown)

    document.addEventListener("keydown", handleKeyDown)

    window.addEventListener("resize", updatePosition)

    window.addEventListener("scroll", updatePosition, true)

    return () => {
      document.removeEventListener("pointerdown", handlePointerDown)

      document.removeEventListener("keydown", handleKeyDown)

      window.removeEventListener("resize", updatePosition)

      window.removeEventListener("scroll", updatePosition, true)
    }
  }, [notifOpen])

  useEffect(() => {
    let cancelled = false
    if (notifOpen) setNotificationLoading(true)
    setNotificationError(null)
    fetchNotifications()
      .then((response) => {
        if (cancelled) return
        setNotifCount(response.pending_count)
        setNotificationTasks(response.items)
      })
      .catch((error: unknown) => {
        if (!cancelled) setNotificationError(safeApiErrorMessage(error))
      })
      .finally(() => {
        if (!cancelled) setNotificationLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [notifOpen])

  useEffect(() => {
    let cancelled = false

    fetchHealthStatus()

      .then((h) => {
        if (!cancelled) {
          setSystemStatus(h.status === "ok" ? "healthy" : "degraded")
        }
      })

      .catch(() => {
        if (!cancelled) setSystemStatus("unavailable")
      })

    return () => {
      cancelled = true
    }
  }, [])

  return (
    <header
      ref={headerRef}
      className="flex flex-col md:flex-row md:items-center justify-between gap-2.5 md:gap-4 px-4 sm:px-6 py-2.5 border-b border-[#DCE7F3] bg-white flex-shrink-0 min-h-[52px] md:h-[52px] w-full min-w-0"
    >
      {/* Top control bar on mobile / Left control group on desktop */}
      <div className="flex items-center justify-between md:justify-start gap-3 w-full md:w-auto min-w-0">
        <div className="flex items-center gap-2">
          {/* Mobile Menu Toggle */}
          <button
            onClick={onToggleMobileNav}
            className="md:hidden p-1.5 text-[#52627A] hover:text-[#071A3D] rounded hover:bg-[#F5FAFF] -ml-1"
            aria-label="Open Mobile Navigation"
          >
            <Menu size={18} />
          </button>

          {/* Mobile Brand Title (< 640px) */}
          <div className="flex items-center gap-2 md:hidden">
            <img src={logoUrl} alt="MDIS" className="w-6 h-6 object-contain" />
            <span className="font-sans text-xs font-[950] uppercase tracking-[0.12em] text-[#146EF5]">
              MDIS
            </span>
          </div>
        </div>

        {/* Mobile Right Quick Controls (< 640px) */}
        <div className="flex items-center gap-2 md:hidden">
          <button
            ref={mobileBellRef}
            onClick={() => setNotifOpen(!notifOpen)}
            aria-label="Notifications"
            aria-expanded={notifOpen}
            aria-controls="notifications-panel"
            className={`relative w-7 h-7 flex items-center justify-center rounded-full border transition-colors ${
              notifOpen
                ? "border-[rgba(20,110,245,0.45)] bg-[rgba(20,110,245,0.12)]"
                : "border-[#DCE7F3] bg-white hover:bg-[#EAF5FF]"
            }`}
          >
            <Bell
              size={16}
              className={notifOpen ? "text-[#146EF5]" : "text-[#52627A]"}
              aria-hidden="true"
            />
            {notifCount > 0 && (
              <span className="absolute -right-1 -top-1 grid min-h-4 min-w-4 place-items-center rounded-full border-2 border-white bg-[#146EF5] px-0.5 text-[9px] font-semibold leading-none text-white" aria-label={`${notifCount} pending review items`}>
                {notifCount > 99 ? "99+" : notifCount}
              </span>
            )}
          </button>
        </div>
      </div>

      {/* Global Search Component: Full width on < 640px, sm:w-[280px], lg:w-[380px] on desktop */}
      <div className="w-full min-w-0 md:w-auto md:min-w-[280px] lg:w-[380px] flex-1 max-w-md">
        <button
          onClick={onOpenSearch}
          className="w-full h-10 sm:h-9 min-w-0 flex items-center justify-between px-3 rounded-md bg-[#EAF5FF] border border-[#DCE7F3] text-xs text-[#52627A] hover:border-[#DCE7F3] transition-colors"
        >
          <div className="flex items-center gap-2 min-w-0 flex-1">
            <Search size={14} className="text-[#52627A] flex-shrink-0" />
            <span className="font-sans truncate">
              Search documents, patients, cases...
            </span>
          </div>
          <kbd className="hidden md:inline-flex px-1.5 py-0.5 text-[10px] font-mono text-[#52627A] bg-white border border-[#DCE7F3] rounded flex-shrink-0">
            ⌘K
          </kbd>
        </button>
      </div>

      {/* Desktop Right Controls (≥ 640px) */}
      <div className="hidden md:flex items-center gap-3 ml-auto flex-shrink-0">
        {/* System status indicator — driven by GET /api/v1/health */}
        {(() => {
          const STATUS_MAP: Record<SystemStatusCode, {
            bg: string
            border: string
            dot: string
            dotClass: string
            text: string
            label: string
          }> = {
            healthy: {
              bg: "bg-[#f0fdf4]",
              border: "border-[#bbf7d0]",
              dot: "bg-[#22c55e]",
              dotClass: "pulse-dot",
              text: "text-[#15803d]",
              label: "All systems operational",
            },

            degraded: {
              bg: "bg-[#fffbeb]",
              border: "border-[#fde68a]",
              dot: "bg-[#d97706]",
              dotClass: "",
              text: "text-[#b45309]",
              label: "Some services degraded",
            },

            unavailable: {
              bg: "bg-[#fef2f2]",
              border: "border-[#fecaca]",
              dot: "bg-[#ef4444]",
              dotClass: "",
              text: "text-[#b91c1c]",
              label: "Service unavailable",
            },

            unknown: {
              bg: "bg-[#EAF5FF]",
              border: "border-[#DCE7F3]",
              dot: "bg-[#52627A]",
              dotClass: "",
              text: "text-[#52627A]",
              label: "Checking status…",
            },
          }

          const s = STATUS_MAP[systemStatus]

          return (
            <div
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full ${s.bg} border ${s.border}`}
            >
              <span
                className={`w-1.5 h-1.5 rounded-full ${s.dot} ${s.dotClass}`}
                aria-hidden="true"
              />
              <span className={`font-mono text-[10px] ${s.text}`}>
                {s.label}
              </span>
            </div>
          )
        })()}

        {/* Notifications Dropdown */}
        <div className="relative">
          <button
            ref={desktopBellRef}
            onClick={() => setNotifOpen(!notifOpen)}
            aria-label="Notifications"
            aria-expanded={notifOpen}
            aria-controls="notifications-panel"
            className={`relative w-8 h-8 rounded-full flex items-center justify-center border transition-colors ${
              notifOpen
                ? "border-[rgba(20,110,245,0.45)] bg-[rgba(20,110,245,0.12)]"
                : "border-[#DCE7F3] bg-white hover:bg-[#EAF5FF]"
            }`}
          >
            <Bell
              size={15}
              className={notifOpen ? "text-[#146EF5]" : "text-[#52627A]"}
              aria-hidden="true"
            />
            {notifCount > 0 && (
              <span className="absolute -right-1 -top-1 grid min-h-4 min-w-4 place-items-center rounded-full border-2 border-white bg-[#146EF5] px-0.5 text-[9px] font-semibold leading-none text-white" aria-label={`${notifCount} pending review items`}>
                {notifCount > 99 ? "99+" : notifCount}
              </span>
            )}
          </button>
        </div>

        {/* Help Icon */}
        <button
          aria-label="Help"
          className="w-8 h-8 rounded-full flex items-center justify-center bg-[#EAF5FF] hover:bg-[#DCE7F3] transition-colors text-[#52627A]"
        >
          <HelpCircle size={15} aria-hidden="true" />
        </button>
      </div>

      {notifOpen && (
        <>
          <button
            type="button"
            aria-label="Close notifications"
            onClick={() => setNotifOpen(false)}
            className="md:hidden fixed inset-0 z-40 bg-[rgba(7,26,61,0.25)]"
          />
          <div
            id="notifications-panel"
            ref={notifPanelRef}
            className="fixed left-3 right-3 md:left-auto md:right-auto md:w-80 max-h-[70vh] overflow-y-auto md:max-h-none bg-white border border-[#DCE7F3] rounded-xl md:rounded-lg shadow-xl z-50 slide-in md:overflow-hidden"
            style={{
              top: notifPosition.top,
              left: window.matchMedia("(min-width: 768px)").matches
                ? notifPosition.left
                : 12,
              right: window.matchMedia("(min-width: 768px)").matches
                ? "auto"
                : 12,
            }}
          >
            <div className="px-4 py-3 border-b border-[#DCE7F3] flex items-center justify-between">
              <span className="font-sans text-sm font-semibold text-[#071A3D]">
                Notifications
              </span>
              {notifCount > 0 && (
                <span className="text-[10px] font-mono text-[#146EF5] bg-[#EAF5FF] px-2 py-0.5 rounded">
                  {notifCount} Pending
                </span>
              )}
            </div>
            <div className="divide-y divide-[#DCE7F3]" aria-live="polite">
              {notificationLoading ? (
                <p className="px-4 py-5 text-center text-xs text-[#52627A]">Loading notifications…</p>
              ) : notificationError ? (
                <p role="alert" className="px-4 py-5 text-center text-xs text-[#B91C1C]">{notificationError}</p>
              ) : notificationTasks.length === 0 ? (
                <p className="px-4 py-5 text-center text-xs text-[#52627A]">No pending review items.</p>
              ) : notificationTasks.map((task) => (
                <button
                  key={task.id}
                  onClick={() => {
                    setNotifOpen(false)

                      onNavigate("review-document", undefined, task.id)
                  }}
                  className="w-full px-4 py-3 flex items-start gap-3 text-left hover:bg-[#EAF5FF] transition-colors"
                >
                  <span className={`mt-1 inline-block h-2 w-2 flex-shrink-0 rounded-full ${task.priority === "high" ? "bg-[#F59E0B]" : "bg-[#146EF5]"}`} aria-hidden="true">
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="text-xs font-medium text-[#071A3D] truncate">
                      {task.priority === "high" ? "High-priority review task" : "Review task requires attention"}
                    </div>
                    <div className="text-[11px] text-[#52627A] mt-0.5">
                      {task.document_type} · {task.priority} priority
                    </div>
                  </div>
                  <time dateTime={task.created_at} className="font-mono text-[9px] text-[#52627A]">
                    {new Date(task.created_at).toLocaleDateString()}
                  </time>
                </button>
              ))}
            </div>
            <div className="p-2 border-t border-[#DCE7F3] bg-[#EAF5FF]">
              <button
                onClick={() => {
                  setNotifOpen(false)

                  onNavigate("review")
                }}
                className="w-full text-center text-xs font-medium text-[#146EF5] py-1 hover:underline"
              >
                Open Review Center →
              </button>
            </div>
          </div>
        </>
      )}
    </header>
  )
}
