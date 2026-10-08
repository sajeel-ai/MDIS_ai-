import React, { useState } from "react"
import { Sidebar } from "../components/navigation/Sidebar"

import { Header } from "../components/navigation/Header"

import { MobileNavigation } from "../components/navigation/MobileNavigation"

import { CommandPalette } from "../components/shared/CommandPalette"

export interface AppLayoutProps {
  children: React.ReactNode

  activeView: string

  onNavigate: (view: string) => void
}

export function AppLayout({
  children,
  activeView,
  onNavigate,
}: AppLayoutProps) {
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)

  return (
    <div className="app-shell-viewport flex overflow-hidden bg-[#F5FAFF] font-sans antialiased text-[#071A3D]">
      {/* Desktop Persistent Sidebar (220px on 1440+, 72px on 768-1023) */}
      <div className="hidden h-full shrink-0 md:block">
        <Sidebar activeView={activeView} onNavigate={onNavigate} />
      </div>

      {/* Mobile Off-Canvas Drawer Navigation (< 768px) */}
      <MobileNavigation
        isOpen={mobileNavOpen}
        onClose={() => setMobileNavOpen(false)}
        activeView={activeView}
        onNavigate={onNavigate}
      />

      {/* Global Command Search Modal */}
      <CommandPalette
        isOpen={searchOpen}
        onClose={() => setSearchOpen(false)}
        onNavigate={onNavigate}
      />

      {/* Main Right Content Panel */}
      <div className="flex-1 flex flex-col overflow-hidden min-w-0">
        <Header
          onOpenSearch={() => setSearchOpen(true)}
          onToggleMobileNav={() => setMobileNavOpen(true)}
          onNavigate={onNavigate}
        />
        <main
          className={`min-h-0 min-w-0 flex-1 overflow-x-hidden bg-[#F5FAFF] ${
            activeView === "clinical"
              ? "overflow-y-hidden p-0"
              : "overflow-y-auto p-4 sm:p-6"
          }`}
        >
          {children}
        </main>
      </div>
    </div>
  )
}
