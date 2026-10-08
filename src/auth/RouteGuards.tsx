import { useEffect, type ReactNode } from "react"
import type { AuthUser } from "../services/api"

export function safeReturnPath(
  candidate: string | null | undefined,
  origin = window.location.origin,
): string {
  if (
    !candidate ||
    !candidate.startsWith("/") ||
    candidate.startsWith("//") ||
    candidate.includes("\\")
  )
    return "/dashboard"
  try {
    const resolved = new URL(candidate, origin)
    return resolved.origin === origin
      ? `${resolved.pathname}${resolved.search}${resolved.hash}`
      : "/dashboard"
  } catch {
    return "/dashboard"
  }
}

export function AuthLoadingScreen({
  message = "Checking your session…",
}: {
  message?: string
}) {
  return (
    <main
      className="flex min-h-screen items-center justify-center bg-[#F5FAFF] px-5 text-sm text-[#52627A]"
      aria-live="polite"
    >
      {message}
    </main>
  )
}

export function AccessRestrictedState({
  onNavigate,
}: {
  onNavigate?: (view: string) => void
}) {
  return (
    <main className="flex min-h-[50vh] items-center justify-center bg-[#F5FAFF] px-5 py-12">
      <section className="w-full max-w-lg rounded-xl border border-[#DCE7F3] bg-white p-8 text-center">
        <h1 className="text-xl font-semibold text-[#071A3D]">
          Access restricted
        </h1>
        <p className="mt-2 text-sm text-[#52627A]">
          You don't have permission to access this resource.
        </p>
        {onNavigate && (
          <button
            type="button"
            onClick={() => onNavigate("dashboard")}
            className="mt-5 rounded-lg bg-[#146EF5] px-4 py-2 text-sm font-medium text-white hover:bg-[#0F5BD6]"
          >
            Return to dashboard
          </button>
        )}
      </section>
    </main>
  )
}

export function ProtectedRoute({
  isLoading,
  isAuthenticated,
  onUnauthenticated,
  children,
}: {
  isLoading: boolean
  isAuthenticated: boolean
  onUnauthenticated: () => void
  children: ReactNode
}) {
  useEffect(() => {
    if (!isLoading && !isAuthenticated) onUnauthenticated()
  }, [isLoading, isAuthenticated, onUnauthenticated])

  if (isLoading) return <AuthLoadingScreen />
  if (!isAuthenticated) return null
  return children
}

export function RoleRoute({
  user,
  allowedRoles,
  children,
}: {
  user: AuthUser | null
  allowedRoles: readonly string[]
  children: ReactNode
}) {
  if (!user || !allowedRoles.includes(user.role))
    return <AccessRestrictedState />
  return children
}
