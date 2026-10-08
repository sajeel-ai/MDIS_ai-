import { useCallback, useEffect, useRef, useState } from "react"
import {
  approveAccountRequest,
  fetchAccountRequests,
  fetchManagedSessions,
  fetchManagedUsers,
  inviteManagedUser,
  rejectAccountRequest,
  revokeManagedSession,
  safeApiErrorMessage,
  setManagedUserActive,
  updateManagedUserRole,
  type AccountRequest,
  type ManagedSession,
  type ManagedUser,
} from "../services/api"
import { AppLayout } from "../layouts/AppLayout"

const roles = ["admin", "clinician", "operator", "reviewer", "viewer"]

function ConfirmDialog({ title, message, confirmLabel = "Confirm", onConfirm, onClose, warning = false }: { title: string; message: string; confirmLabel?: string; onConfirm: () => void; onClose: () => void; warning?: boolean }) {
  const closeRef = useRef<HTMLButtonElement>(null)
  useEffect(() => { closeRef.current?.focus() }, [])
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose()
      if (event.key === "Tab") {
        const buttons = Array.from(document.querySelectorAll<HTMLButtonElement>('[role="dialog"] button'))
        if (buttons.length && event.shiftKey && document.activeElement === buttons[0]) { event.preventDefault(); buttons[buttons.length - 1].focus() }
        else if (buttons.length && !event.shiftKey && document.activeElement === buttons[buttons.length - 1]) { event.preventDefault(); buttons[0].focus() }
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [onClose])
  return <div className="fixed inset-0 z-50 grid place-items-center bg-[rgba(7,26,61,0.35)] p-4" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
    <section role="dialog" aria-modal="true" aria-labelledby="confirm-title" className="w-full max-w-md rounded-xl border border-[#DCE7F3] bg-white p-5 shadow-xl">
      <h2 id="confirm-title" className="font-semibold text-[#071A3D]">{title}</h2>
      <p className={`mt-2 text-sm ${warning ? "text-[#B45309]" : "text-[#52627A]"}`}>{message}</p>
      <div className="mt-5 flex justify-end gap-2"><button ref={closeRef} type="button" onClick={onClose} className="min-h-11 rounded-lg border border-[#DCE7F3] px-4">Cancel</button><button type="button" onClick={onConfirm} className="min-h-11 rounded-lg bg-[#146EF5] px-4 font-semibold text-white">{confirmLabel}</button></div>
    </section>
  </div>
}

export function AdminUsersPage({
  onNavigate,
}: {
  onNavigate: (view: string) => void
}) {
  const [users, setUsers] = useState<ManagedUser[]>([])
  const [requests, setRequests] = useState<AccountRequest[]>([])
  const [selected, setSelected] = useState<ManagedUser | null>(null)
  const [sessions, setSessions] = useState<ManagedSession[]>([])
  const [error, setError] = useState("")
  const [notice, setNotice] = useState("")
  const [busy, setBusy] = useState(false)
  const [loadingUsers, setLoadingUsers] = useState(true)
  const [loadingRequests, setLoadingRequests] = useState(true)
  const [usersError, setUsersError] = useState("")
  const [requestsError, setRequestsError] = useState("")
  const [search, setSearch] = useState("")
  const [query, setQuery] = useState("")
  const [userPage, setUserPage] = useState(1)
  const [requestPage, setRequestPage] = useState(1)
  const [userTotal, setUserTotal] = useState(0)
  const [requestTotal, setRequestTotal] = useState(0)
  const [userFilters, setUserFilters] = useState({ role: "", status: "", mfa: "" })
  const [approvalRoles, setApprovalRoles] = useState<Record<string, string>>({})
  const [confirm, setConfirm] = useState<{ title: string; message: string; action: () => void; warning?: boolean } | null>(null)
  const rejectionRef = useRef<HTMLTextAreaElement>(null)
  const [rejecting, setRejecting] = useState<AccountRequest | null>(null)
  const [rejectionReason, setRejectionReason] = useState("")
  const [email, setEmail] = useState("")
  const [fullName, setFullName] = useState("")
  const [role, setRole] = useState("clinician")
  const [confirmPrivileged, setConfirmPrivileged] = useState(false)
  const privilegedRole = role === "admin" || role === "operator"
  const reloadUsers = useCallback(async () => {
    setLoadingUsers(true); setUsersError("")
    try { const result = await fetchManagedUsers({ page: userPage, pageSize: 25, q: query, ...userFilters }); const page = Array.isArray(result) ? { items: result, total: result.length } : result; setUsers(page.items); setUserTotal(page.total) }
    catch (e) { setUsersError(safeApiErrorMessage(e, "Access restricted (admin only)")) }
    finally { setLoadingUsers(false) }
  }, [userPage, query, userFilters])
  const reloadRequests = useCallback(async () => {
    setLoadingRequests(true); setRequestsError("")
    try { const result = await fetchAccountRequests({ page: requestPage, pageSize: 25, q: query }); const page = Array.isArray(result) ? { items: result, total: result.length } : result; setRequests(page.items); setRequestTotal(page.total) }
    catch (e) { setRequestsError(safeApiErrorMessage(e, "Access restricted (admin only)")) }
    finally { setLoadingRequests(false) }
  }, [requestPage, query])
  const reload = useCallback(async () => { await Promise.allSettled([reloadUsers(), reloadRequests()]) }, [reloadUsers, reloadRequests])
  useEffect(() => {
    const timer = window.setTimeout(() => { setQuery(search.trim()); setUserPage(1); setRequestPage(1) }, 250)
    return () => window.clearTimeout(timer)
  }, [search])
  useEffect(() => { void reload() }, [reload])
  useEffect(() => { if (rejecting) rejectionRef.current?.focus() }, [rejecting])
  useEffect(() => {
    if (!rejecting) return
    const trap = (event: KeyboardEvent) => {
      if (event.key === "Escape") { setRejecting(null); return }
      if (event.key !== "Tab") return
      const dialog = document.querySelector<HTMLElement>('[aria-labelledby="reject-title"]')
      const focusable = dialog ? Array.from(dialog.querySelectorAll<HTMLElement>('textarea,button:not([disabled])')) : []
      if (!focusable.length) return
      const first = focusable[0]; const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
    }
    window.addEventListener("keydown", trap)
    return () => window.removeEventListener("keydown", trap)
  }, [rejecting])
  const run = async (fn: () => Promise<unknown>, done: string) => {
    setBusy(true)
    setError("")
    setNotice("")
    try {
      await fn()
      if (done) setNotice(done)
      await reload()
      if (selected)
        setSessions(await fetchManagedSessions(selected.id).catch(() => []))
    } catch (e) {
      setError(safeApiErrorMessage(e, "Access restricted (admin only)"))
    } finally {
      setBusy(false)
    }
  }
  const selectUser = async (user: ManagedUser) => {
    setSelected(user)
    setSessions([])
    try {
      setSessions(await fetchManagedSessions(user.id))
    } catch (e) {
      setError(safeApiErrorMessage(e, "Access restricted (admin only)"))
    }
  }
  const invite = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError("")
    try {
      const result = await inviteManagedUser({
        email,
        full_name: fullName,
        role,
        confirm_privileged: confirmPrivileged,
      })
      setNotice(
        result.email_delivery === "not_configured"
          ? "Invitation created; email delivery not configured. Configure email delivery before sending the invitation link."
          : "Invitation queued for delivery.",
      )
      setEmail("")
      setFullName("")
      setConfirmPrivileged(false)
      await reload()
    } catch (e) {
      setError(safeApiErrorMessage(e, "Access restricted (admin only)"))
    } finally {
      setBusy(false)
    }
  }
  const approve = (account: AccountRequest, approvedRole: string) => {
    const privileged = approvedRole === "admin" || approvedRole === "operator"
    setConfirm({ title: "Approve account request", message: privileged ? `Approve ${account.email} as ${approvedRole}? This grants privileged access and requires MFA enrollment.` : `Approve ${account.email} as ${approvedRole}?`, warning: privileged, action: () => { setConfirm(null); void run(async () => {
        const result = await approveAccountRequest(account.id, approvedRole, privileged)
        setNotice(
          result.email_delivery === "not_configured"
            ? "Account approved; email delivery is not configured."
            : "Account approved and notification queued.",
        )
      }, "") } })
  }
  const reject = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!rejecting || !rejectionReason.trim()) return
    await run(async () => {
      const result = await rejectAccountRequest(
        rejecting.id,
        rejectionReason.trim(),
      )
      setNotice(
        result.email_delivery === "not_configured"
          ? "Request rejected; email delivery is not configured."
          : "Request rejected and notification queued.",
      )
    }, "")
    setRejecting(null)
    setRejectionReason("")
  }
  return (
    <AppLayout activeView="users" onNavigate={onNavigate}>
      <section className="mx-auto w-full max-w-[1440px] min-w-0 space-y-5 pb-8" aria-labelledby="admin-users-title">
        <div>
          <h1
            id="admin-users-title"
            className="text-xl font-bold text-[#071A3D]"
          >
            User Management
          </h1>
          <p className="mt-1 text-sm text-[#52627A]">
            Organization users and active sessions
          </p>
        </div>
        <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto_auto_auto]">
          <label className="sr-only" htmlFor="user-search">Search users</label>
          <input id="user-search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search name or email" className="min-h-11 rounded-lg border border-[#DCE7F3] bg-white px-3 text-sm" />
          <select aria-label="Filter by role" value={userFilters.role} onChange={(event) => { setUserPage(1); setUserFilters({ ...userFilters, role: event.target.value }) }} className="min-h-11 rounded-lg border border-[#DCE7F3] bg-white px-3 text-sm"><option value="">All roles</option>{roles.map((item) => <option key={item}>{item}</option>)}</select>
          <select aria-label="Filter by status" value={userFilters.status} onChange={(event) => { setUserPage(1); setUserFilters({ ...userFilters, status: event.target.value }) }} className="min-h-11 rounded-lg border border-[#DCE7F3] bg-white px-3 text-sm"><option value="">All statuses</option><option value="active">Active</option><option value="inactive">Inactive</option></select>
          <select aria-label="Filter by MFA" value={userFilters.mfa} onChange={(event) => { setUserPage(1); setUserFilters({ ...userFilters, mfa: event.target.value }) }} className="min-h-11 rounded-lg border border-[#DCE7F3] bg-white px-3 text-sm"><option value="">All MFA</option><option value="enabled">MFA enabled</option><option value="disabled">MFA disabled</option></select>
        </div>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4" aria-label="User management summary">
          <div className="rounded-xl border border-[#DCE7F3] bg-white p-3"><p className="text-xs text-[#52627A]">Total users</p><p className="mt-1 text-xl font-semibold text-[#071A3D]">{userTotal}</p></div>
          <div className="rounded-xl border border-[#DCE7F3] bg-white p-3"><p className="text-xs text-[#52627A]">Loaded active</p><p className="mt-1 text-xl font-semibold text-[#071A3D]">{users.filter((user) => user.is_active).length}</p></div>
          <div className="rounded-xl border border-[#DCE7F3] bg-white p-3"><p className="text-xs text-[#52627A]">Pending requests</p><p className="mt-1 text-xl font-semibold text-[#071A3D]">{requestTotal}</p></div>
          <div className="rounded-xl border border-[#DCE7F3] bg-white p-3"><p className="text-xs text-[#52627A]">Admins without MFA</p><p className="mt-1 text-xl font-semibold text-[#B45309]">{users.filter((user) => user.role === "admin" && !user.mfa_enabled).length}</p></div>
        </div>
        {error && (
          <p
            role="alert"
            aria-live="polite"
            className="rounded-lg border border-[#FECACA] bg-[#FEF2F2] p-3 text-sm text-[#B91C1C]"
          >
            {error}
          </p>
        )}
        {notice && (
          <p
            role="status"
            className="rounded-lg border border-[#DCE7F3] bg-[#EAF5FF] p-3 text-sm text-[#071A3D]"
          >
            {notice}
          </p>
        )}
        <section
          aria-labelledby="account-requests-title"
          className="rounded-xl border border-[#DCE7F3] bg-white p-4"
        >
          <h2
            id="account-requests-title"
            className="font-semibold text-[#071A3D]"
          >
            Account requests
            {requests.length > 0 && (
              <span className="ml-2 rounded-full bg-[#EAF5FF] px-2 py-0.5 align-middle text-xs font-medium text-[#52627A]">
                {requests.length} pending
              </span>
            )}
          </h2>
          {requestsError && <div role="alert" className="mt-3 rounded-lg bg-[#FEF2F2] p-3 text-sm text-[#B91C1C]">{requestsError} <button type="button" onClick={() => void reloadRequests()} className="ml-2 font-semibold underline">Retry</button></div>}
          {loadingRequests ? <p className="mt-3 text-sm text-[#52627A]">Loading account requests…</p> : requests.length ? (
            <ul className="mt-3 max-h-72 divide-y divide-[#DCE7F3] overflow-y-auto pr-1">
              {requests.map((account) => (
                <li
                  key={account.id}
                  className="grid min-w-0 gap-3 py-4 xl:grid-cols-[minmax(0,1fr)_auto] xl:items-center"
                >
                  <div className="min-w-0">
                    <p className="font-medium text-[#071A3D]">
                      {account.full_name || account.email}
                    </p>
                    <p className="break-all text-sm text-[#52627A]">
                      {account.email} ·{" "}
                      {account.professional_role_requested ||
                        "Role not provided"}
                    </p>
                    {account.requested_organization_name && (
                      <p className="mt-1 text-sm text-[#B45309]">
                        Organization verification required:{" "}
                        {account.requested_organization_name}
                      </p>
                    )}
                  </div>
                  <div className="flex min-w-0 flex-wrap items-center gap-2">
                    <label
                      className="sr-only"
                      htmlFor={`approval-role-${account.id}`}
                    >
                      Role for {account.email}
                    </label>
                    <select
                      id={`approval-role-${account.id}`}
                      value={approvalRoles[account.id] ?? "clinician"}
                      onChange={(event) => setApprovalRoles({ ...approvalRoles, [account.id]: event.target.value })}
                      className="min-h-11 rounded-lg border border-[#DCE7F3] px-2"
                    >
                      {roles.map((item) => (
                          <option key={item}>{item}</option>
                        ))}
                    </select>
                    <button
                      disabled={
                        busy || Boolean(account.requested_organization_name)
                      }
                      className="min-h-11 rounded-lg bg-[#146EF5] px-3 font-medium text-white disabled:opacity-50"
                      onClick={() => approve(account, approvalRoles[account.id] ?? "clinician")}
                    >
                      Approve
                    </button>
                    <button
                      disabled={busy}
                      className="min-h-11 rounded-lg border border-[#DCE7F3] px-3 text-[#B91C1C]"
                      onClick={() => {
                        setRejecting(account)
                        setRejectionReason("")
                      }}
                    >
                      Reject
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-sm text-[#52627A]">
              No verified account requests. Only email-verified registration requests appear here.
            </p>
          )}
          {requestTotal > 25 && <div className="mt-3 flex items-center justify-between text-xs text-[#52627A]"><span>Showing {(requestPage - 1) * 25 + 1}-{Math.min(requestPage * 25, requestTotal)} of {requestTotal}</span><button type="button" disabled={requestPage === 1} onClick={() => setRequestPage((page) => page - 1)} className="rounded border px-2 py-1 disabled:opacity-40">Previous</button><button type="button" disabled={requestPage * 25 >= requestTotal} onClick={() => setRequestPage((page) => page + 1)} className="rounded border px-2 py-1 disabled:opacity-40">Next</button></div>}
        </section>
        <form
          onSubmit={invite}
          className="grid gap-3 rounded-xl border border-[#DCE7F3] bg-white p-4 sm:grid-cols-2 lg:grid-cols-4"
        >
          <h2 className="sm:col-span-2 lg:col-span-4 text-base font-semibold text-[#071A3D]">
            Invite user
          </h2>
          <label className="text-sm">
            Full name
            <input
              required
              maxLength={128}
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              className="mt-1 h-11 w-full rounded-lg border border-[#DCE7F3] px-3"
            />
          </label>
          <label className="text-sm">
            Email
            <input
              required
              type="email"
              autoComplete="email"
              maxLength={256}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="mt-1 h-11 w-full rounded-lg border border-[#DCE7F3] px-3"
            />
          </label>
          <label className="text-sm">
            Role
            <select
              value={role}
              onChange={(e) => { setRole(e.target.value); setConfirmPrivileged(false) }}
              className="mt-1 h-11 w-full rounded-lg border border-[#DCE7F3] px-3"
            >
              {roles.filter((item) => item !== "admin" && item !== "operator").map((item) => (
                <option key={item}>{item}</option>
              ))}
            </select>
          </label>
          {privilegedRole && <label className="flex items-center gap-2 text-xs text-[#B45309] lg:col-span-4"><input type="checkbox" checked={confirmPrivileged} onChange={(event) => setConfirmPrivileged(event.target.checked)} className="h-4 w-4" />I understand this grants a privileged {role} role and the user must enroll in MFA.</label>}
          <button
            disabled={busy || (privilegedRole && !confirmPrivileged)}
            className="min-h-11 self-end rounded-lg bg-[#146EF5] px-4 font-semibold text-white disabled:opacity-50"
          >
            {busy ? "Sending…" : "Send invitation"}
          </button>
        </form>
        <section aria-labelledby="managed-users-title" className="overflow-hidden rounded-xl border border-[#DCE7F3] bg-white">
          <div className="flex items-center justify-between gap-3 border-b border-[#DCE7F3] px-4 py-3">
            <div>
              <h2 id="managed-users-title" className="font-semibold text-[#071A3D]">Organization users</h2>
              <p className="mt-0.5 text-xs text-[#52627A]">Active accounts and session management</p>
            </div>
            <span className="shrink-0 rounded-full bg-[#EAF5FF] px-2.5 py-1 text-xs font-medium text-[#52627A]">
              {users.length} {users.length === 1 ? "user" : "users"}
            </span>
          </div>
          {usersError && <div role="alert" className="m-4 rounded-lg bg-[#FEF2F2] p-3 text-sm text-[#B91C1C]">{usersError} <button type="button" onClick={() => void reloadUsers()} className="ml-2 font-semibold underline">Retry</button></div>}
          {loadingUsers ? <p className="px-4 py-8 text-sm text-[#52627A]">Loading users…</p> : <>
          <div className="space-y-3 p-3 md:hidden">
            {users.map((user) => <article key={`card-${user.id}`} className="rounded-lg border border-[#DCE7F3] p-3">
              <p className="font-medium text-[#071A3D]">{user.full_name || user.email}</p><p className="mt-0.5 break-all text-xs text-[#52627A]">{user.email}</p>
              <div className="mt-3 grid gap-2"><label className="text-xs text-[#52627A]">Role<select aria-label={`Role for ${user.email}`} value={user.role} disabled={busy} onChange={(event) => { const next = event.target.value; setConfirm({ title: "Change user role", message: `Change ${user.email}'s role to ${next}?`, warning: next === "admin" || next === "operator", action: () => { setConfirm(null); void run(() => updateManagedUserRole(user.id, next, next === "admin" || next === "operator", user.updated_at), "Role updated.") } }) }} className="mt-1 h-10 w-full rounded-lg border border-[#DCE7F3] px-2" /> </label>
              <p className="text-xs text-[#52627A]">Status: <span className="font-medium text-[#071A3D]">{user.pending_approval ? "Pending approval" : user.is_active ? "Active" : "Inactive"}</span> · MFA: <span className="font-medium text-[#071A3D]">{user.mfa_enabled ? "Enabled" : "Not enabled"}</span></p>
              <div className="flex flex-wrap gap-2"><button type="button" className="min-h-11 rounded-lg border border-[#DCE7F3] px-3 text-[#146EF5]" onClick={() => void selectUser(user)}>Sessions{typeof user.session_count === "number" ? ` (${user.session_count})` : ""}</button><button type="button" className="min-h-11 rounded-lg border border-[#DCE7F3] px-3" disabled={busy || user.pending_approval} onClick={() => setConfirm({ title: user.is_active ? "Deactivate user" : "Reactivate user", message: `${user.is_active ? "Deactivate" : "Reactivate"} ${user.email}?`, action: () => { setConfirm(null); void run(() => setManagedUserActive(user.id, !user.is_active, user.updated_at), user.is_active ? "User deactivated." : "User reactivated.") } })}>{user.is_active ? "Deactivate" : "Reactivate"}</button></div>
            </div></article>)}
          </div>
          <div className="hidden overflow-x-auto md:block">
          <table className="w-full min-w-[700px] text-left text-sm">
            <thead className="sticky top-0 z-10 bg-[#EAF5FF] text-xs uppercase text-[#52627A]">
              <tr>
                <th className="p-3">User</th>
                <th className="p-3">Role</th>
                <th className="p-3">Status</th>
                <th className="p-3">MFA</th>
                <th className="p-3">Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr key={user.id} className="border-t border-[#DCE7F3]">
                  <td className="p-3">
                    <span className="font-medium text-[#071A3D]">
                      {user.full_name || user.email}
                    </span>
                    <span className="block text-xs text-[#52627A]">
                      {user.email}
                    </span>
                  </td>
                  <td className="p-3">
                    <label className="sr-only" htmlFor={`role-${user.id}`}>
                      Role for {user.email}
                    </label>
                    <select
                      id={`role-${user.id}`}
                      value={user.role}
                      disabled={busy}
                      onChange={(e) => {
                        const next = e.target.value
                        setConfirm({ title: "Change user role", message: `Change ${user.email}'s role to ${next}?`, warning: next === "admin" || next === "operator", action: () => { setConfirm(null); void run(() => updateManagedUserRole(user.id, next, next === "admin" || next === "operator", user.updated_at), "Role updated.") } })
                      }}
                      className="h-10 rounded-lg border border-[#DCE7F3] px-2"
                    >
                      {roles.map((item) => (
                        <option key={item}>{item}</option>
                      ))}
                    </select>
                  </td>
                  <td className="p-3">
                    {user.pending_approval
                      ? "Pending approval"
                      : user.is_active
                        ? "Active"
                        : "Inactive"}
                  </td>
                  <td className="p-3">
                    {user.mfa_enabled ? "Enabled" : "Not enabled"}
                  </td>
                  <td className="p-3">
                    <div className="flex flex-wrap gap-2">
                      <button
                        className="min-h-11 rounded-lg border border-[#DCE7F3] px-3 text-[#146EF5]"
                        onClick={() => void selectUser(user)}
                      >
                        Sessions
                      </button>
                      <button
                        className="min-h-11 rounded-lg border border-[#DCE7F3] px-3 text-[#071A3D]"
                        disabled={busy || user.pending_approval}
                        onClick={() => setConfirm({ title: user.is_active ? "Deactivate user" : "Reactivate user", message: `${user.is_active ? "Deactivate" : "Reactivate"} ${user.email}?`, action: () => { setConfirm(null); void run(() => setManagedUserActive(user.id, !user.is_active, user.updated_at), user.is_active ? "User deactivated." : "User reactivated.") } })}
                      >
                        {user.is_active ? "Deactivate" : "Reactivate"}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div></>}
          {!users.length && (
            <div className="border-t border-[#DCE7F3] px-4 py-8 text-center text-sm text-[#52627A]">
              No organization users are available yet. Send an invitation above to add one.
            </div>
          )}
          {userTotal > 25 && <div className="flex items-center justify-between border-t border-[#DCE7F3] px-4 py-3 text-xs text-[#52627A]"><span>Showing {(userPage - 1) * 25 + 1}-{Math.min(userPage * 25, userTotal)} of {userTotal}</span><div className="flex gap-2"><button type="button" disabled={userPage === 1} onClick={() => setUserPage((page) => page - 1)} className="rounded border px-2 py-1 disabled:opacity-40">Previous</button><button type="button" disabled={userPage * 25 >= userTotal} onClick={() => setUserPage((page) => page + 1)} className="rounded border px-2 py-1 disabled:opacity-40">Next</button></div></div>}
        </section>
        {selected && (
          <section
            aria-labelledby="sessions-title"
            className="rounded-xl border border-[#DCE7F3] bg-white p-4"
          >
            <h2 id="sessions-title" className="font-semibold text-[#071A3D]">
              Active sessions: {selected.email}
            </h2>
            {sessions.length ? (
              <ul className="mt-3 divide-y divide-[#DCE7F3]">
                {sessions.map((s) => (
                  <li
                    key={s.family_id}
                    className="flex flex-wrap items-center justify-between gap-3 py-3 text-sm"
                  >
                    <span>
                      Created {new Date(s.created_at).toLocaleString()} ·
                      expires {new Date(s.expires_at).toLocaleString()}
                    </span>
                    <button
                      className="min-h-11 rounded-lg border border-[#DCE7F3] px-3 text-[#B91C1C]"
                      disabled={busy}
                      onClick={() => setConfirm({ title: "Revoke session", message: "The user will need to sign in again. Continue?", action: () => { setConfirm(null); void run(() => revokeManagedSession(selected.id, s.family_id), "Session revoked.") } })}
                    >
                      Revoke session
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-3 text-sm text-[#52627A]">No active sessions.</p>
            )}
          </section>
        )}
        {rejecting && (
          <div className="fixed inset-0 z-50 grid place-items-center bg-[rgba(7,26,61,0.35)] p-4" onMouseDown={(event) => { if (event.target === event.currentTarget) setRejecting(null) }}>
            <section
              role="dialog"
              aria-modal="true"
              aria-labelledby="reject-title"
              className="w-full max-w-md rounded-xl border border-[#DCE7F3] bg-white p-5"
            >
              <h2 id="reject-title" className="font-semibold text-[#071A3D]">
                Reject account request
              </h2>
              <p className="mt-1 text-sm text-[#52627A]">
                Provide a reason for {rejecting.email}.
              </p>
              <form onSubmit={reject}>
                <label className="mt-4 block text-sm text-[#071A3D]">
                  Reason
                  <textarea
                    ref={rejectionRef}
                    required
                    maxLength={500}
                    value={rejectionReason}
                    onChange={(event) => setRejectionReason(event.target.value)}
                    className="mt-2 min-h-24 w-full rounded-lg border border-[#DCE7F3] p-3"
                  />
                </label>
                <div className="mt-4 flex justify-end gap-2">
                  <button
                    type="button"
                    className="min-h-11 rounded-lg border border-[#DCE7F3] px-4"
                    onClick={() => setRejecting(null)}
                  >
                    Cancel
                  </button>
                  <button
                    disabled={busy || !rejectionReason.trim()}
                    className="min-h-11 rounded-lg bg-[#146EF5] px-4 font-semibold text-white"
                  >
                    Confirm rejection
                  </button>
                </div>
              </form>
            </section>
          </div>
        )}
        {confirm && <ConfirmDialog title={confirm.title} message={confirm.message} confirmLabel={confirm.title.includes("Approve") ? "Approve" : confirm.title.includes("Reject") ? "Reject" : confirm.title.includes("Deactivate") ? "Deactivate" : confirm.title.includes("Reactivate") ? "Reactivate" : confirm.title.includes("Revoke") ? "Revoke session" : "Save changes"} warning={confirm.warning} onClose={() => setConfirm(null)} onConfirm={confirm.action} />}
      </section>
    </AppLayout>
  )
}
