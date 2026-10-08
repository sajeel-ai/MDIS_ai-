import React, { useEffect } from 'react';
import { X } from 'lucide-react';

export interface DialogProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  maxWidth?: 'sm' | 'md' | 'lg' | 'xl';
}

export function Dialog({ isOpen, onClose, title, children, maxWidth = 'md' }: DialogProps) {
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

  const widthClasses = {
    sm: 'max-w-sm',
    md: 'max-w-md',
    lg: 'max-w-lg',
    xl: 'max-w-2xl',
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4 animate-fade-in">
      <div
        className={`w-full ${widthClasses[maxWidth]} bg-white rounded-lg border border-[#DCE7F3] shadow-xl overflow-hidden flex flex-col max-h-[90vh] slide-in`}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-[#DCE7F3] bg-[#EAF5FF]">
          <h2 className="text-sm font-semibold text-[#071A3D] font-sans">{title}</h2>
          <button
            onClick={onClose}
            className="p-1 text-[#52627A] hover:text-[#071A3D] rounded hover:bg-[#DCE7F3] transition-colors"
          >
            <X size={16} />
          </button>
        </div>
        <div className="p-5 overflow-y-auto flex-1">{children}</div>
      </div>
    </div>
  );
}
