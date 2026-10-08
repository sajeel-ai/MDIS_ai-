import React, { useEffect } from 'react';
import { X } from 'lucide-react';

export interface DrawerProps {
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  children: React.ReactNode;
  position?: 'left' | 'right';
  width?: string;
  mobileNavigation?: boolean;
}

export function Drawer({
  isOpen,
  onClose,
  title,
  children,
  position = 'right',
  width = 'w-80 sm:w-96',
  mobileNavigation = false,
}: DrawerProps) {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    if (isOpen) {
      document.addEventListener('keydown', handleKeyDown);
    }
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const posClass = position === 'right' ? 'right-0' : 'left-0';
  return (
    <div className="fixed inset-0 z-50 overflow-hidden">
      <div
        className={mobileNavigation
          ? 'absolute inset-0 bg-[rgba(7,26,61,0.45)] backdrop-blur-xs transition-opacity'
          : 'absolute inset-0 bg-black/30 backdrop-blur-xs transition-opacity'}
        onClick={onClose}
      />
      <div
        role={mobileNavigation ? 'dialog' : undefined}
        aria-modal={mobileNavigation ? true : undefined}
        aria-label={mobileNavigation ? 'Navigation' : undefined}
        className={mobileNavigation
          ? `mobile-sidebar-drawer mobile-navigation-slide-in fixed top-0 left-0 z-50 flex ${width} max-w-[85vw] flex-col overflow-hidden rounded-r-2xl bg-[#071A3D] shadow-[8px_0_32px_rgba(7,26,61,0.35)]`
          : `fixed inset-y-0 ${posClass} max-w-full ${width} bg-white shadow-2xl flex flex-col border-l border-[#DCE7F3] z-50`}
      >
        {title && !mobileNavigation && (
          <div className="flex items-center justify-between px-5 py-4 border-b border-[#DCE7F3] bg-[#EAF5FF]">
            <h3 className="text-sm font-semibold text-[#071A3D]">{title}</h3>
            <button
              onClick={onClose}
              aria-label="Close drawer"
              className="p-1 text-[#52627A] hover:text-[#071A3D] rounded hover:bg-[#DCE7F3] transition-colors"
            >
              <X size={16} />
            </button>
          </div>
        )}
        <div className={mobileNavigation ? 'flex-1 min-h-0 overflow-hidden bg-[#071A3D] p-0' : 'flex-1 overflow-y-auto p-5'}>{children}</div>
      </div>
    </div>
  );
}
