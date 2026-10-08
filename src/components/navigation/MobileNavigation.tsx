import React from 'react';
import { Drawer } from '../ui/Drawer';
import { Sidebar } from './Sidebar';

export interface MobileNavigationProps {
  isOpen: boolean;
  onClose: () => void;
  activeView: string;
  onNavigate: (view: string) => void;
}

export function MobileNavigation({ isOpen, onClose, activeView, onNavigate }: MobileNavigationProps) {
  return (
    <Drawer isOpen={isOpen} onClose={onClose} position="left" width="w-[300px]" mobileNavigation>
      <div className="flex h-full min-h-0 w-full">
        <Sidebar
          activeView={activeView}
          onNavigate={(v) => {
            onNavigate(v);
            onClose();
          }}
          isMobileDrawer
          onClose={onClose}
        />
      </div>
    </Drawer>
  );
}
