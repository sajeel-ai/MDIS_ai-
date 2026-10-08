import React, { useState, useEffect } from 'react';
import { Search, FileText, User, CheckSquare, GitBranch, ArrowRight } from 'lucide-react';

export interface CommandPaletteProps {
  isOpen: boolean;
  onClose: () => void;
  onNavigate: (view: string) => void;
}

export function CommandPalette({ isOpen, onClose, onNavigate }: CommandPaletteProps) {
  const [query, setQuery] = useState('');

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        isOpen ? onClose() : null;
      }
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const COMMANDS = [
    { category: 'Quick Navigation', label: 'Open Clinical Workspace', icon: <FileText size={14} />, view: 'clinical' },
    { category: 'Quick Navigation', label: 'Open Review Center Queue', icon: <CheckSquare size={14} />, view: 'review' },
    { category: 'Quick Navigation', label: 'View AI Operations & Telemetry', icon: <GitBranch size={14} />, view: 'aiops' },
    { category: 'Recent Documents', label: 'Discharge Summary — Margaret T. (CL-102938)', icon: <FileText size={14} />, view: 'clinical' },
    { category: 'Recent Documents', label: 'Emergency Note — Aisha K. (CL-102944)', icon: <FileText size={14} />, view: 'clinical' },
    { category: 'Patients', label: 'Robert H. (MRN-551034)', icon: <User size={14} />, view: 'timeline' },
  ];

  const filtered = COMMANDS.filter((c) => c.label.toLowerCase().includes(query.toLowerCase()));

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto overscroll-contain pt-20 bg-black/40 backdrop-blur-xs p-4 animate-fade-in">
      <div className="command-palette-panel min-h-0 w-full max-w-xl bg-white rounded-lg border border-[#DCE7F3] shadow-2xl overflow-hidden flex flex-col slide-in">
        {/* Input */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-[#DCE7F3] bg-white">
          <Search size={18} className="text-[#52627A]" />
          <input
            type="text"
            autoFocus
            placeholder="Type a command or search clinical records..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="w-full text-sm font-sans text-[#071A3D] outline-none placeholder-[#52627A]"
          />
          <kbd className="px-1.5 py-0.5 text-[10px] font-mono text-[#52627A] bg-[#F5FAFF] border border-[#DCE7F3] rounded">
            ESC
          </kbd>
        </div>

        {/* Results */}
        <div className="min-h-0 flex-1 overflow-y-auto p-2">
          {filtered.length === 0 ? (
            <div className="p-6 text-center text-xs text-[#52627A]">No clinical records or commands found</div>
          ) : (
            filtered.map((item, index) => (
              <button
                key={index}
                onClick={() => {
                  onNavigate(item.view);
                  onClose();
                }}
                className="w-full flex items-center justify-between px-3 py-2.5 rounded-md hover:bg-[#EAF5FF] text-left text-xs transition-colors group"
              >
                <div className="flex items-center gap-3">
                  <span className="text-[#52627A] group-hover:text-[#146EF5]">{item.icon}</span>
                  <span className="font-medium text-[#071A3D]">{item.label}</span>
                </div>
                <div className="flex items-center gap-1.5 text-[10px] text-[#52627A] font-mono group-hover:text-[#146EF5]">
                  <span>{item.category}</span>
                  <ArrowRight size={12} />
                </div>
              </button>
            ))
          )}
        </div>
        <div className="px-4 py-2 border-t border-[#DCE7F3] bg-[#EAF5FF] flex items-center justify-between text-[11px] text-[#52627A]">
          <span>Navigate with arrow keys</span>
          <span>Press Enter to select</span>
        </div>
      </div>
    </div>
  );
}
