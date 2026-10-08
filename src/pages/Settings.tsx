import React, { useEffect, useState } from 'react';
import { AppLayout } from '../layouts/AppLayout';
import { Card, CardHeader, CardTitle } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { ShieldCheck, Users, Database, Bell, UserRound, KeyRound, LogOut } from 'lucide-react';
import { fetchReviewPolicy, type ReviewPolicy } from '../services/api';
import { useAuth } from '../auth/AuthProvider';

export interface SettingsPageProps {
  onNavigate: (view: string) => void;
}

export function SettingsPage({ onNavigate }: SettingsPageProps) {
  const auth = useAuth();
  const [activeSection, setActiveSection] = useState('Account');
  const [logoutError, setLogoutError] = useState<string | null>(null);
  const [loggingOut, setLoggingOut] = useState(false);
  const [reviewPolicy, setReviewPolicy] = useState<ReviewPolicy | null>(null);
  useEffect(() => {
    fetchReviewPolicy().then(setReviewPolicy).catch(() => setReviewPolicy(null));
  }, []);
  const sections = [
    { label: 'Account', icon: <UserRound size={16} /> },
    { label: 'Security & Audit Configuration', icon: <ShieldCheck size={16} /> },
    { label: 'User Roles & Access Control', icon: <Users size={16} /> },
    { label: 'Data Retention & Storage', icon: <Database size={16} /> },
    { label: 'Clinical Alerts & Notifications', icon: <Bell size={16} /> },
  ];

  return (
    <AppLayout activeView="settings" onNavigate={onNavigate}>
      <div className="space-y-6">
        <div>
          <h1 className="text-xl font-bold text-[#071A3D]">Organization Settings &amp; Security</h1>
          <p className="text-xs text-[#52627A] mt-0.5">
            Configure system parameters, user role permissions, and security policies
          </p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Settings Sub-nav */}
          <Card className="lg:col-span-1 p-2 space-y-1 h-fit">
            {sections.map((item) => (
              <button
                key={item.label}
                onClick={() => setActiveSection(item.label)}
                aria-current={activeSection === item.label ? 'page' : undefined}
                className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-md border-l-2 text-xs font-medium transition-colors text-left ${
                  activeSection === item.label
                    ? 'bg-[#EAF5FF] text-[#071A3D] border-[#146EF5]'
                    : 'text-[#52627A] border-transparent hover:bg-[#EAF5FF]'
                }`}
              >
                {item.icon}
                <span>{item.label}</span>
              </button>
            ))}
          </Card>

          {/* Details Content */}
          <div className="lg:col-span-2 space-y-4">
            {activeSection === 'Account' && (
              <Card>
                <CardHeader>
                  <CardTitle>Account</CardTitle>
                </CardHeader>
                <div className="px-5 pb-5">
                  <div className="flex items-center gap-3 rounded-lg border border-[#DCE7F3] bg-[#F5FAFF] p-4">
                    <div className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-[#146EF5] text-base font-semibold text-white" aria-hidden="true">
                      {(auth.user?.display_name?.trim() || auth.user?.email || 'A').charAt(0).toUpperCase()}
                    </div>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold text-[#071A3D]">{auth.user?.display_name?.trim() || auth.user?.email || 'Account'}</p>
                      <p className="truncate text-xs text-[#52627A]">{auth.user?.email}</p>
                      <p className="mt-1 text-[11px] capitalize text-[#52627A]">{auth.user?.role.replace(/[_-]/g, ' ')}</p>
                    </div>
                  </div>
                  {logoutError && <p role="alert" className="mt-3 text-sm text-[#B91C1C]">{logoutError}</p>}
                  <div className="mt-4 flex flex-wrap gap-3">
                    <button
                      type="button"
                      onClick={() => onNavigate('change-password')}
                      className="inline-flex min-h-10 items-center gap-2 rounded-lg border border-[#DCE7F3] px-4 text-sm font-medium text-[#071A3D] hover:bg-[#EAF5FF] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#146EF5]"
                    >
                      <KeyRound size={16} aria-hidden="true" />
                      Change password
                    </button>
                    <button
                      type="button"
                      disabled={loggingOut}
                      onClick={async () => {
                        setLoggingOut(true);
                        setLogoutError(null);
                        try {
                          await auth.logout();
                          onNavigate('login');
                        } catch {
                          setLogoutError('Unable to sign out. Please retry.');
                        } finally {
                          setLoggingOut(false);
                        }
                      }}
                      className="inline-flex min-h-10 items-center gap-2 rounded-lg border border-[#DCE7F3] px-4 text-sm font-medium text-[#071A3D] hover:bg-[#EAF5FF] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#146EF5] disabled:cursor-wait disabled:opacity-60"
                    >
                      <LogOut size={16} aria-hidden="true" />
                      {loggingOut ? 'Signing out…' : 'Sign out'}
                    </button>
                  </div>
                </div>
              </Card>
            )}

            {activeSection === 'Security & Audit Configuration' && (
            <Card>
              <CardHeader>
                <CardTitle>Security Controls</CardTitle>
                <Badge variant="neutral">Deployment-Managed</Badge>
              </CardHeader>
              <p className="text-xs text-[#52627A] px-5 pb-3 leading-relaxed">
                Security configuration — including encryption at rest, transport security, and
                compliance controls — is managed by the deployment environment and infrastructure
                team. Contact your system administrator to verify active security policies.
              </p>
              <div className="space-y-3 text-xs text-[#52627A] px-5 pb-5">
                <div className="flex items-center justify-between p-3 bg-[#EAF5FF] rounded-md border border-[#DCE7F3]">
                  <div>
                    <div className="font-semibold text-[#071A3D]">Review Policy</div>
                    <div className="text-[11px] text-[#52627A]">
                      Effective review routing policy (read only)
                      {reviewPolicy && ` · Review threshold ${Math.round(reviewPolicy.confidence_threshold * 100)}% · High priority ${Math.round(reviewPolicy.high_priority_threshold * 100)}%`}
                    </div>
                  </div>
                  <Badge variant="neutral">{reviewPolicy?.policy ?? 'Not available'}</Badge>
                </div>
                <div className="flex items-center justify-between p-3 bg-[#EAF5FF] rounded-md border border-[#DCE7F3]">
                  <div>
                    <div className="font-semibold text-[#071A3D]">Data-at-Rest Encryption</div>
                    <div className="text-[11px] text-[#52627A]">
                      Encryption configuration managed by deployment environment
                    </div>
                  </div>
                <Badge variant="neutral">Env-Configured</Badge>
                </div>
                <div className="flex items-center justify-between p-3 bg-[#EAF5FF] rounded-md border border-[#DCE7F3]">
                  <div>
                    <div className="font-semibold text-[#071A3D]">Transport Security</div>
                    <div className="text-[11px] text-[#52627A]">
                      TLS configuration enforced at infrastructure level
                    </div>
                  </div>
                <Badge variant="neutral">Env-Configured</Badge>
                </div>
              </div>
            </Card>
            )}

            {activeSection === 'Data Retention & Storage' && (
            <Card>
              <CardHeader>
                <CardTitle>PHI Data Retention &amp; Purge Policy</CardTitle>
              </CardHeader>
              <div className="space-y-3 px-5 pb-5">
                <div className="flex justify-between items-center text-xs">
                  <span className="text-[#52627A] font-medium">Audit Log Retention</span>
                  <span className="font-mono font-semibold text-[#071A3D]">7 Years</span>
                </div>
                <div className="flex justify-between items-center text-xs">
                  <span className="text-[#52627A] font-medium">Unvalidated Case Scratchpad</span>
                  <span className="font-mono font-semibold text-[#071A3D]">30 Days</span>
                </div>
              </div>
            </Card>
            )}

            {(activeSection === 'User Roles & Access Control' || activeSection === 'Clinical Alerts & Notifications') && (
              <Card>
                <CardHeader>
                  <CardTitle>{activeSection}</CardTitle>
                </CardHeader>
                <p className="text-xs text-[#52627A]">This section is not available yet.</p>
              </Card>
            )}
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
