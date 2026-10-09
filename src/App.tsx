import { useCallback, useEffect, useState } from "react"
import { DashboardPage } from "./pages/Dashboard"
import { DocumentsPage } from "./pages/Documents"
import { ClinicalWorkspacePage } from "./pages/ClinicalWorkspace"
import { ReviewCenterPage } from "./pages/ReviewCenter"
import { ReviewDocumentPage } from "./pages/ReviewDocument"
import { WorkflowsPage } from "./pages/Workflows"
import { IntegrationsPage } from "./pages/Integrations"
import { AIOperationsPage } from "./pages/AIOperations"
import { SettingsPage } from "./pages/Settings"
import { PatientTimeline } from "./views/PatientTimeline"
import { AppLayout } from "./layouts/AppLayout"
import { ExtractionView } from "./views/Placeholders"
import {
  AnalyticsView,
  AuditView,
  PipelineView,
} from "./views/OperationalViews"
import { AuthProvider, useAuth } from "./auth/AuthProvider"
import {
  AccessRestrictedState,
  ProtectedRoute,
  RoleRoute,
  safeReturnPath,
} from "./auth/RouteGuards"
import { AuthLoadingScreen } from "./auth/RouteGuards"
import { LoginPage } from "./pages/Login"
import { AcceptInvitationPage, ChangePasswordPage, ForbiddenPage, ForgotPasswordPage, MfaSetupPage, MfaVerifyPage, RegisterPage, ResetPasswordPage, SessionExpiredPage } from "./pages/AuthFlows"
import { AdminUsersPage } from "./pages/AdminUsers"

if (import.meta.env.PROD && import.meta.env.VITE_AUTH_BYPASS === "true") {
  throw new Error("VITE_AUTH_BYPASS must not be enabled in a production build.")
}

type View = "dashboard" | "documents" | "clinical" | "review" | "review-document" | "workflows" | "integrations" | "aiops" | "settings" | "timeline" | "extraction" | "analytics" | "audit" | "pipeline" | "login" | "forgot" | "reset" | "invite" | "change-password" | "mfa-setup" | "mfa-verify" | "expired" | "forbidden" | "register" | "users"

type RouteState = {
  view: View
  path: string
  documentId: string | null
  reviewTaskId: string | null
}
const ROLE_NAMES = [
  "admin",
  "clinician",
  "operator",
  "reviewer",
  "viewer",
] as const
const RESTRICTED_VIEW_ROLES: Partial<Record<View, readonly string[]>> = {
  aiops: ["admin", "operator"],
  pipeline: ["admin", "operator"],
  analytics: ["admin", "operator"],
  audit: ["admin", "operator"],
  users: ["admin"],
}

function parseRoute(pathname: string): RouteState {
  const cleanPath = pathname.length > 1 ? pathname.replace(/\/$/, "") : pathname
  if (cleanPath === "/login")
    return {
      view: "login",
      path: cleanPath,
      documentId: null,
      reviewTaskId: null,
    }
  const clinicalMatch = cleanPath.match(/^\/clinical(?:\/([^/]+))?$/)
  if (clinicalMatch)
    return {
      view: "clinical",
      path: cleanPath,
      documentId: clinicalMatch[1]
        ? decodeURIComponent(clinicalMatch[1])
        : null,
      reviewTaskId: null,
    }
  const reviewMatch = cleanPath.match(/^\/review(?:\/([^/]+))?$/)
  if (reviewMatch)
    return {
      view: reviewMatch[1] ? "review-document" : "review",
      path: cleanPath,
      documentId: null,
      reviewTaskId: reviewMatch[1] ? decodeURIComponent(reviewMatch[1]) : null,
    }
  const pathViews: Record<string, View> = {
    "/": "dashboard",
    "/dashboard": "dashboard",
    "/documents": "documents",
    "/patients": "timeline",
    "/timeline": "timeline",
    "/workflows": "workflows",
    "/integrations": "integrations",
    "/ai-operations": "aiops",
    "/aiops": "aiops",
    "/settings": "settings",
    "/ai-extraction": "extraction",
    "/extraction": "extraction",
    "/analytics": "analytics",
    "/audit": "audit",
    "/pipeline": "pipeline",
    "/forgot-password": "forgot",
    "/reset-password": "reset",
    "/accept-invitation": "invite",
    "/change-password": "change-password",
    "/mfa/setup": "mfa-setup",
    "/mfa/verify": "mfa-verify",
    "/session-expired": "expired",
    "/forbidden": "forbidden",
    "/register": "register",
    "/admin/users": "users",
  }
  const reviewDocumentMatch = cleanPath.match(/^\/review\/document\/([^/]+)$/)
  if (reviewDocumentMatch)
    return {
      view: "review-document",
      path: cleanPath,
      documentId: null,
      reviewTaskId: decodeURIComponent(reviewDocumentMatch[1]),
    }
  const view = pathViews[cleanPath] ?? "dashboard"
  return { view, path: cleanPath, documentId: null, reviewTaskId: null }
}

function readRoute(): RouteState {
  return parseRoute(window.location.pathname)
}

function pathForView(
  view: string,
  documentId?: string,
  reviewTaskId?: string,
): string {
  if (view === "clinical" && documentId)
    return `/clinical/${encodeURIComponent(documentId)}`
  if (view === "review" && reviewTaskId)
    return `/review/${encodeURIComponent(reviewTaskId)}`
  if (view === "review-document" && reviewTaskId)
    return `/review/document/${encodeURIComponent(reviewTaskId)}`
  const paths: Record<string, string> = {
    login: "/login",
    dashboard: "/dashboard",
    documents: "/documents",
    clinical: "/clinical",
    review: "/review",
    workflows: "/workflows",
    integrations: "/integrations",
    aiops: "/ai-operations",
    settings: "/settings",
    timeline: "/patients",
    extraction: "/ai-extraction",
    analytics: "/analytics",
    audit: "/audit",
    pipeline: "/pipeline",
    users: "/admin/users",
    "change-password": "/change-password",
  }
  return paths[view] ?? "/dashboard"
}

function AppContent() {
  const auth = useAuth()
  const [route, setRoute] = useState<RouteState>(() => readRoute())
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([])
  const [resetEmail, setResetEmail] = useState("")

  const changePath = useCallback(
    (path: string, replace = false) => {
      if (replace) window.history.replaceState(null, "", path)
      else window.history.pushState(null, "", path)
      setRoute(readRoute())
      auth.clearAccessRestricted()
    },
    [auth.clearAccessRestricted],
  )

  const navigate = useCallback(
    (view: string, documentId?: string, reviewTaskId?: string) => {
      changePath(pathForView(view, documentId, reviewTaskId))
    },
    [changePath],
  )

  useEffect(() => {
    const onPopState = () => setRoute(readRoute())
    window.addEventListener("popstate", onPopState)
    return () => window.removeEventListener("popstate", onPopState)
  }, [])

  useEffect(() => {
    if (auth.authError === "Your session has expired. Please sign in again.")
      changePath("/session-expired", true)
  }, [auth.authError, changePath])

  const onUnauthenticated = useCallback(() => {
    const search = new URLSearchParams(window.location.search)
    const desiredPath =
      route.view === "login"
        ? safeReturnPath(search.get("returnTo"))
        : safeReturnPath(
            `${route.path}${window.location.search}${window.location.hash}`,
          )
    changePath(`/login?returnTo=${encodeURIComponent(desiredPath)}`, true)
  }, [changePath, route])

  useEffect(() => {
    if (auth.isLoading || !auth.isAuthenticated || route.view !== "login")
      return
    const desired = safeReturnPath(
      new URLSearchParams(window.location.search).get("returnTo"),
    )
    changePath(desired, true)
  }, [auth.isAuthenticated, auth.isLoading, changePath, route.view])

  const afterLogin = (codes?: string[]) => {
    if (codes?.length) setRecoveryCodes(codes)
    const desired = safeReturnPath(
      new URLSearchParams(window.location.search).get("returnTo"),
    )
    changePath(desired, true)
  }

  const onResetRequested = (email: string) => {
    setResetEmail(email.trim().toLowerCase())
    changePath("/reset-password?step=code")
  }

  const publicPages: Partial<Record<View, React.ReactNode>> = {
    forgot: <ForgotPasswordPage />,
    reset: <ResetPasswordPage initialEmail={resetEmail} />,
    invite: <AcceptInvitationPage />,
    "mfa-setup": <MfaSetupPage onComplete={afterLogin} />,
    "mfa-verify": <MfaVerifyPage onAuthenticated={() => afterLogin()} />,
    expired: <SessionExpiredPage />,
    forbidden: <ForbiddenPage />,
    register: <RegisterPage />,
  }
  if (publicPages[route.view]) return publicPages[route.view]
  if (auth.isLoading) return <AuthLoadingScreen />
  if (route.view === "login" && !auth.isAuthenticated)
    return (
      <LoginPage
        onAuthenticated={afterLogin}
        onResetRequested={onResetRequested}
      />
    )
  if (route.view === "login" && auth.isAuthenticated)
    return <AuthLoadingScreen message="Opening your workspace…" />

  let content
  switch (route.view) {
    case "dashboard":
      content = <DashboardPage onNavigate={navigate} />
      break
    case "documents":
      content = <DocumentsPage onNavigate={navigate} />
      break
    case "clinical":
      content = (
        <ClinicalWorkspacePage
          onNavigate={navigate}
          documentId={route.documentId}
        />
      )
      break
    case "review":
      content = (
        <ReviewCenterPage
          onNavigate={navigate}
          reviewTaskId={route.reviewTaskId}
        />
      )
      break
    case "review-document":
      content = (
        <ReviewDocumentPage
          onNavigate={navigate}
          reviewTaskId={route.reviewTaskId}
        />
      )
      break
    case "workflows":
      content = <WorkflowsPage onNavigate={navigate} />
      break
    case "integrations":
      content = <IntegrationsPage onNavigate={navigate} />
      break
    case "aiops":
      content = <AIOperationsPage onNavigate={navigate} />
      break
    case "settings":
      content = <SettingsPage onNavigate={navigate} />
      break
    case "change-password":
      content = <ChangePasswordPage onDone={() => changePath("/login", true)} />
      break
    case "users":
      content = <AdminUsersPage onNavigate={navigate} />
      break
    case "timeline":
      content = (
        <AppLayout activeView="timeline" onNavigate={navigate}>
          <PatientTimeline />
        </AppLayout>
      )
      break
    case "extraction":
      content = (
        <AppLayout activeView="extraction" onNavigate={navigate}>
          <ExtractionView onNavigate={navigate} />
        </AppLayout>
      )
      break
    case "analytics":
      content = (
        <AppLayout activeView="analytics" onNavigate={navigate}>
          <AnalyticsView />
        </AppLayout>
      )
      break
    case "audit":
      content = (
        <AppLayout activeView="audit" onNavigate={navigate}>
          <AuditView />
        </AppLayout>
      )
      break
    case "pipeline":
      content = (
        <AppLayout activeView="pipeline" onNavigate={navigate}>
          <PipelineView />
        </AppLayout>
      )
      break
    default:
      content = <DashboardPage onNavigate={navigate} />
  }

  // Integrations handles its own admin/operator health 403 states so users can
  // still see which individual checks are restricted versus unavailable.
  if (auth.accessRestricted && route.view !== "integrations") {
    content = (
      <AppLayout activeView={route.view} onNavigate={navigate}>
        <AccessRestrictedState onNavigate={navigate} />
      </AppLayout>
    )
  }

  const guardedContent = (
    <RoleRoute
      user={auth.user}
      allowedRoles={RESTRICTED_VIEW_ROLES[route.view] ?? ROLE_NAMES}
    >
      {content}
    </RoleRoute>
  )

  return (
    <ProtectedRoute
      isLoading={auth.isLoading}
      isAuthenticated={auth.isAuthenticated}
      onUnauthenticated={onUnauthenticated}
    >
      <>
        {recoveryCodes.length > 0 && (
          <div
            role="alert"
            className="fixed inset-x-4 top-4 z-50 mx-auto max-w-lg rounded-xl border border-[#DCE7F3] bg-white p-5 text-sm text-[#071A3D] shadow-xl"
          >
            <strong className="block">Save your recovery codes</strong>
            <p className="my-2 text-[#52627A]">
              Each code can be used once if you cannot access your
              authenticator.
            </p>
            <pre className="grid grid-cols-2 gap-2 whitespace-pre-wrap rounded-lg bg-[#F5FAFF] p-3">
              {recoveryCodes.join("\n")}
            </pre>
            <button
              className="mt-3 rounded-lg bg-[#146EF5] px-4 py-2 text-white"
              onClick={() => setRecoveryCodes([])}
            >
              I have saved these codes
            </button>
          </div>
        )}
        {guardedContent}
      </>
    </ProtectedRoute>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  )
}
