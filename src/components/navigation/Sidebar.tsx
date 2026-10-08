import React, { useEffect, useState } from 'react';
import {
  LayoutDashboard,
  FileSpreadsheet,
  Clock,
  CheckSquare,
  Sparkles,
  Activity,
  GitBranch,
  BarChart3,
  ShieldCheck,
  Settings,
  ActivitySquare,
  X,
  Users,
} from 'lucide-react';
import { fetchReviewStats, type ReviewStats } from '../../services/api';
import logoUrl from '../../public/Glossy Blue Ribbon M Emblem.png';
import { useOptionalAuth } from '../../auth/AuthProvider';

export interface SidebarProps {
  activeView: string;
  onNavigate: (view: string) => void;
  collapsed?: boolean;
  isMobileDrawer?: boolean;
  onClose?: () => void;
}

interface NavItem {
  id: string;
  label: string;
  icon: React.ReactNode;
  badgeKey?: keyof ReviewStats;
  section?: string;
  adminOnly?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { id: 'dashboard', label: 'Dashboard', icon: <LayoutDashboard size={16} /> },
  { id: 'clinical', label: 'Clinical Workspace', section: 'Clinical', icon: <FileSpreadsheet size={16} /> },
  { id: 'documents', label: 'Documents', icon: <FileSpreadsheet size={16} /> },
  { id: 'timeline', label: 'Clinical Timeline', icon: <Clock size={16} /> },
  // badgeKey: 'pending' will pull from live ReviewStats
  { id: 'review', label: 'Review Center', badgeKey: 'pending', icon: <CheckSquare size={16} /> },
  { id: 'extraction', label: 'AI Extraction', section: 'AI', icon: <Sparkles size={16} /> },
  { id: 'aiops', label: 'AI Operations', icon: <Activity size={16} /> },
  { id: 'pipeline', label: 'Pipeline', icon: <Activity size={16} /> },
  { id: 'workflows', label: 'Workflows', icon: <GitBranch size={16} /> },
  { id: 'integrations', label: 'Integrations', section: 'System', icon: <ActivitySquare size={16} /> },
  { id: 'analytics', label: 'Analytics', icon: <BarChart3 size={16} /> },
  { id: 'audit', label: 'Audit & Compliance', icon: <ShieldCheck size={16} /> },
  { id: 'settings', label: 'Settings', icon: <Settings size={16} /> },
  { id: 'users', label: 'User Management', section: 'Administration', icon: <Users size={16} />, adminOnly: true },
];

export function Sidebar({ activeView, onNavigate, isMobileDrawer = false, onClose }: SidebarProps) {
  const [reviewStats, setReviewStats] = useState<ReviewStats | null>(null);
  const auth = useOptionalAuth();
  const accountName = auth?.user?.display_name?.trim() || auth?.user?.email || 'Account';
  const accountInitial = accountName.charAt(0).toUpperCase();
  const accountRole = auth?.user?.role
    ? auth.user.role.replace(/[_-]/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
    : 'Signed out';
  const navItems = NAV_ITEMS.filter((item) => !item.adminOnly || auth?.hasRole('admin'));
  let currentSection = '';

  useEffect(() => {
    let cancelled = false;
    fetchReviewStats()
      .then((s) => { if (!cancelled) setReviewStats(s); })
      .catch(() => { /* silently leave badge hidden on error */ });
    return () => { cancelled = true; };
  }, []);

  return (
    <aside className={`bg-[#071A3D] flex flex-col ${isMobileDrawer ? 'flex-1 min-h-0 min-w-0 w-full' : 'h-full shrink-0 transition-all duration-200 w-[220px] md:w-[72px] lg:w-[220px]'} border-r border-[#0E2A5C]`}>
      {/* Brand Header */}
      <div className={isMobileDrawer
        ? 'mobile-drawer-brand-header flex w-full shrink-0 items-center justify-between border-b border-[rgba(255,255,255,0.08)] px-4'
        : 'px-4 py-3.5 border-b border-[#0E2A5C] flex items-center gap-2.5'}>
        <img src={logoUrl} alt="MDIS" className="w-7 h-7 object-contain shrink-0" />
        <div className={`min-w-0 flex-1 ${isMobileDrawer ? '' : 'md:hidden lg:block'}`}>
          <div className="font-sans text-[16px] font-bold uppercase tracking-[0.12em] truncate text-white">
            MDIS
          </div>
          <div className="text-[#8FA5CC] text-[10px] font-mono tracking-widest uppercase">INTELLIGENCE</div>
        </div>
        {isMobileDrawer && (
          <button
            type="button"
            onClick={onClose}
            aria-label="Close navigation"
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-[#B8C7E6] transition-colors hover:bg-[rgba(255,255,255,0.10)] hover:text-white focus-visible:bg-[rgba(255,255,255,0.10)] focus-visible:text-white"
          >
            <X size={20} aria-hidden="true" />
          </button>
        )}
      </div>

      {/* Navigation List */}
      <nav
        aria-label="Main navigation"
        className={isMobileDrawer
          ? 'mobile-drawer-scroll min-h-0 flex-1 overflow-y-auto px-3 py-2'
          : 'flex-1 overflow-y-auto py-3 sidebar-scroll'}
      >
        {navItems.map((item) => {
          const showSection = item.section && item.section !== currentSection;
          const firstSection = Boolean(showSection && !currentSection);
          if (item.section) currentSection = item.section;
          const isActive = activeView === item.id;

          // Resolve live badge count — only show when > 0
          const badgeCount =
            item.badgeKey && reviewStats !== null ? reviewStats[item.badgeKey] : undefined;
          const showBadge = typeof badgeCount === 'number' && badgeCount > 0;

          return (
            <React.Fragment key={item.id}>
              {showSection && (
                <div className={isMobileDrawer
                  ? `px-3 pt-5 pb-2 text-[10px] font-mono tracking-[0.12em] text-[#8FA5CC] uppercase font-semibold ${firstSection ? '' : 'border-t border-[rgba(255,255,255,0.08)]'}`
                  : 'text-[#8FA5CC] text-[9px] font-mono tracking-wider px-5 pt-3.5 pb-1.5 uppercase font-semibold md:hidden lg:block'}>
                  {item.section}
                </div>
              )}
              <button
                onClick={() => onNavigate(item.id)}
                title={item.label}
                aria-current={isActive ? 'page' : undefined}
                className={isMobileDrawer
                  ? `mobile-drawer-nav-item relative flex min-h-[44px] w-full items-center gap-3 rounded-[10px] px-3 text-left text-sm transition-colors ${isActive
                    ? 'bg-[#12366F] font-medium text-white'
                    : 'bg-transparent font-normal text-[#B8C7E6] hover:bg-[#12366F] hover:text-white active:bg-[#12366F]'}`
                  : `w-full flex items-center gap-3 transition-colors px-5 md:px-0 lg:px-5 md:justify-center lg:justify-start py-2.5 md:py-3 lg:py-2.5 ${isActive
                    ? 'bg-[#12366F] text-white border-l-2 border-[#146EF5]'
                    : 'text-[#B8C7E6] hover:text-white hover:bg-[#12366F] border-l-2 border-transparent'}`}
              >
                {isMobileDrawer && isActive && (
                  <span className="absolute left-0 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-full bg-[#146EF5]" aria-hidden="true" />
                )}
                <span className={isMobileDrawer
                  ? (isActive ? 'text-[#16C7E8]' : 'text-[#8FA5CC]')
                  : (isActive ? 'text-[#146EF5]' : 'opacity-80')}
                  aria-hidden="true"
                >
                  {isMobileDrawer && React.isValidElement(item.icon)
                    ? React.cloneElement(item.icon as React.ReactElement<{ size?: number }>, { size: 20 })
                    : item.icon}
                </span>
                <span className={isMobileDrawer
                  ? 'min-w-0 flex-1 truncate font-sans text-sm'
                  : 'flex-1 text-left text-xs font-sans truncate md:hidden lg:inline'}>
                  {item.label}
                </span>
                {showBadge && (
                  <span
                    className={`px-1.5 py-0.5 text-white bg-[#146EF5] font-mono text-[10px] min-w-5 text-center md:hidden lg:inline-block ${isMobileDrawer ? 'rounded-full' : 'rounded'}`}
                    aria-label={`${badgeCount} pending reviews`}
                  >
                    {badgeCount}
                  </span>
                )}
              </button>
            </React.Fragment>
          );
        })}
      </nav>

      {/* User Profile Footer — identity from session (currently unauthenticated: shows placeholder) */}
      <div className={isMobileDrawer
        ? 'mobile-drawer-footer shrink-0 rounded-xl border border-[rgba(255,255,255,0.08)] bg-[rgba(255,255,255,0.05)]'
        : 'p-3 border-t border-[#0E2A5C]'}>
        <div className="flex items-center gap-2.5 md:justify-center lg:justify-start">
          <div className="w-7 h-7 rounded-full bg-[#146EF5] flex items-center justify-center text-white text-xs font-semibold font-sans flex-shrink-0">
            {accountInitial}
          </div>
          <div className="min-w-0 flex-1 md:hidden lg:block">
            <div className={isMobileDrawer ? 'truncate font-sans text-sm font-medium text-white' : 'text-[#DCE7F3] text-xs font-sans font-medium truncate'}>{accountName}</div>
            <div className={isMobileDrawer ? 'truncate font-sans text-xs text-[#B8C7E6]' : 'text-[#B8C7E6] text-[9px] font-mono truncate'}>{accountRole}</div>
          </div>
        </div>
      </div>
    </aside>
  );
}
