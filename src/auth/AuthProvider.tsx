import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react"
import {
  ApiError,
  beginMfaSetup as beginMfaSetupRequest,
  enableMfa as enableMfaRequest,
  fetchCurrentUser,
  login as loginRequest,
  loginWithMfa as loginWithMfaRequest,
  logout as logoutRequest,
  refreshAuthSession,
  type AuthUser,
} from "../services/api"

type AuthContextValue = {
  user: AuthUser | null
  isAuthenticated: boolean
  isLoading: boolean
  authError: string | null
  accessRestricted: boolean
  inactivityWarning: boolean
  login: (
    email: string,
    password: string,
    rememberMe: boolean,
    code?: string,
  ) => Promise<AuthUser>
  logout: () => Promise<void>
  refreshSession: () => Promise<boolean>
  hasRole: (...roles: string[]) => boolean
  beginMfaSetup: () => Promise<string>
  enableMfa: (code: string) => Promise<string[]>
  clearAccessRestricted: () => void
  continueSession: () => Promise<boolean>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function authErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 401)
    return "Invalid email or password."
  if (error instanceof ApiError && error.status === 403)
    return "You don't have permission to access this resource."
  return "Unable to connect to the authentication service."
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [authError, setAuthError] = useState<string | null>(null)
  const [accessRestricted, setAccessRestricted] = useState(false)
  const [inactivityWarning, setInactivityWarning] = useState(false)
  const inactivityDialogRef = useRef<HTMLElement>(null)

  const refreshSession = useCallback(async () => {
    setIsLoading(true)
    try {
      const currentUser = await fetchCurrentUser()
      setUser(currentUser)
      setAuthError(null)
      return true
    } catch (error) {
      setUser(null)
      if (
        error instanceof ApiError &&
        (error.status === 401 || error.status === 403)
      ) {
        setAuthError(null)
      } else {
        setAuthError("Unable to connect to the authentication service.")
      }
      return false
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    let initialCheck = true
    const onExpired = () => {
      setUser(null)
      if (!initialCheck)
        setAuthError("Your session has expired. Please sign in again.")
    }
    const onLoggedOut = () => {
      setUser(null)
      setAuthError(null)
    }
    const onAccessRestricted = () => setAccessRestricted(true)

    window.addEventListener("cognate-auth-expired", onExpired)
    window.addEventListener("cognate-auth-logout", onLoggedOut)
    window.addEventListener("cognate-access-restricted", onAccessRestricted)
    void refreshSession().finally(() => {
      initialCheck = false
    })
    return () => {
      window.removeEventListener("cognate-auth-expired", onExpired)
      window.removeEventListener("cognate-auth-logout", onLoggedOut)
      window.removeEventListener(
        "cognate-access-restricted",
        onAccessRestricted,
      )
    }
  }, [refreshSession])

  const login = useCallback(
    async (
      email: string,
      password: string,
      rememberMe: boolean,
      code?: string,
    ) => {
      const authenticatedUser = code
        ? await loginWithMfaRequest(email, password, code, rememberMe)
        : await loginRequest(email, password, rememberMe)
      setUser(authenticatedUser)
      setAuthError(null)
      setAccessRestricted(false)
      return authenticatedUser
    },
    [],
  )

  const logout = useCallback(async () => {
    await logoutRequest()
    setUser(null)
    setAuthError(null)
    setAccessRestricted(false)
  }, [])

  const continueSession = useCallback(async () => {
    try {
      const currentUser = await refreshAuthSession()
      setUser(currentUser)
      setInactivityWarning(false)
      return true
    } catch {
      setUser(null)
      setInactivityWarning(false)
      setAuthError("Your session has expired. Please sign in again.")
      return false
    }
  }, [])

  useEffect(() => {
    if (!inactivityWarning) return
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null
    inactivityDialogRef.current?.querySelector<HTMLElement>("button")?.focus()
    return () => previous?.focus()
  }, [inactivityWarning])

  useEffect(() => {
    if (!user) { setInactivityWarning(false); return }
    const configured = Number(import.meta.env.VITE_AUTH_INACTIVITY_MINUTES)
    const idleMs = (Number.isFinite(configured) && configured > 0 ? configured : 30) * 60_000
    const warningMs = Math.min(2 * 60_000, Math.floor(idleMs / 3))
    let warningTimer: number
    let logoutTimer: number
    const reset = () => {
      window.clearTimeout(warningTimer)
      window.clearTimeout(logoutTimer)
      setInactivityWarning(false)
      warningTimer = window.setTimeout(() => setInactivityWarning(true), Math.max(0, idleMs - warningMs))
      logoutTimer = window.setTimeout(() => {
        void logoutRequest().catch(() => undefined).finally(() => {
          setUser(null)
          setInactivityWarning(false)
          setAuthError("Your session has expired. Please sign in again.")
        })
      }, idleMs)
    }
    const events: (keyof WindowEventMap)[] = ["pointerdown", "keydown", "touchstart", "wheel"]
    events.forEach(event => window.addEventListener(event, reset, { passive: true }))
    reset()
    return () => {
      window.clearTimeout(warningTimer); window.clearTimeout(logoutTimer)
      events.forEach(event => window.removeEventListener(event, reset))
    }
  }, [user, logout])

  const beginMfaSetup = useCallback(() => beginMfaSetupRequest(), [])
  const enableMfa = useCallback(async (code: string) => {
    const recoveryCodes = await enableMfaRequest(code)
    const currentUser = await fetchCurrentUser()
    setUser(currentUser)
    setAuthError(null)
    return recoveryCodes
  }, [])
  const clearAccessRestricted = useCallback(
    () => setAccessRestricted(false),
    [],
  )

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      isAuthenticated: user !== null,
      isLoading,
      authError,
      accessRestricted,
      inactivityWarning,
      login,
      logout,
      refreshSession,
      hasRole: (...roles) => Boolean(user && roles.includes(user.role)),
      beginMfaSetup,
      enableMfa,
      clearAccessRestricted,
      continueSession,
    }),
    [
      user,
      isLoading,
      authError,
      accessRestricted,
      inactivityWarning,
      login,
      logout,
      refreshSession,
      beginMfaSetup,
      enableMfa,
      clearAccessRestricted,
      continueSession,
    ],
  )

  return <AuthContext.Provider value={value}>{children}{inactivityWarning && user && <div className="fixed inset-0 z-[100] grid place-items-center bg-[rgba(7,26,61,0.35)] p-4"><section ref={inactivityDialogRef} role="alertdialog" aria-modal="true" aria-labelledby="idle-title" aria-describedby="idle-description" onKeyDown={event => { if (event.key !== "Tab") return; const controls = inactivityDialogRef.current?.querySelectorAll<HTMLElement>("button"); if (!controls?.length) return; const first = controls[0], last = controls[controls.length - 1]; if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() } else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() } }} className="w-full max-w-md rounded-xl border border-[#DCE7F3] bg-white p-6 shadow-xl"><h2 id="idle-title" className="text-lg font-semibold text-[#071A3D]">Still there?</h2><p id="idle-description" className="mt-2 text-sm text-[#52627A]">You will be signed out soon due to inactivity.</p><div className="mt-5 flex flex-wrap justify-end gap-3"><button className="min-h-11 rounded-lg border border-[#DCE7F3] px-4 text-[#52627A]" onClick={() => void logout().catch(() => undefined)}>Sign out</button><button className="min-h-11 rounded-lg bg-[#146EF5] px-4 font-semibold text-white" onClick={() => void continueSession()}>Stay signed in</button></div></section></div>}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) throw new Error("useAuth must be used inside AuthProvider")
  return context
}

export function useOptionalAuth(): AuthContextValue | null {
  return useContext(AuthContext)
}
