import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const authApi = vi.hoisted(() => ({
  fetchCurrentUser: vi.fn(),
  login: vi.fn(),
  loginWithMfa: vi.fn(),
  logout: vi.fn(),
  beginMfaSetup: vi.fn(),
  enableMfa: vi.fn(),
  requestPasswordReset: vi.fn(),
  fetchAuthConfig: vi.fn(),
  refreshAuthSession: vi.fn(),
  ApiError: class ApiError extends Error {
    constructor(
      readonly status: number,
      message: string,
      readonly data?: unknown,
    ) {
      super(message)
    }
  },
}))

vi.mock("../services/api", () => authApi)

import { AuthProvider, useAuth } from "../auth/AuthProvider"
import {
  AccessRestrictedState,
  ProtectedRoute,
  RoleRoute,
  safeReturnPath,
} from "../auth/RouteGuards"
import { LoginPage } from "../pages/Login"

const signedInUser = {
  id: "synthetic-user",
  email: "clinician@example.test",
  display_name: "Synthetic Clinician",
  role: "clinician",
}

function AuthStateHarness() {
  const auth = useAuth()
  if (auth.isLoading) return <div>Checking your session…</div>
  if (auth.accessRestricted) return <AccessRestrictedState />
  return (
    <div>
      {auth.isAuthenticated ? `signed in as ${auth.user?.email}` : "signed out"}
      {auth.authError && <p role="alert">{auth.authError}</p>}
      <button onClick={() => void auth.logout().catch(() => undefined)}>
        Sign out test
      </button>
    </div>
  )
}

describe("frontend authentication core", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    authApi.fetchCurrentUser.mockResolvedValue(signedInUser)
    authApi.logout.mockResolvedValue(undefined)
    authApi.beginMfaSetup.mockResolvedValue("otpauth://synthetic")
    authApi.enableMfa.mockResolvedValue(["synthetic-recovery-code"])
    authApi.fetchAuthConfig.mockResolvedValue({
      self_registration_enabled: false,
    })
    authApi.refreshAuthSession.mockResolvedValue(signedInUser)
  })

  afterEach(() => vi.restoreAllMocks())

  it("does not render protected children while the startup session check is loading", async () => {
    let resolveSession: (user: typeof signedInUser) => void = () => undefined
    authApi.fetchCurrentUser.mockReturnValue(
      new Promise((resolve) => {
        resolveSession = resolve
      }),
    )
    render(
      <AuthProvider>
        <AuthStateHarness />
      </AuthProvider>,
    )
    expect(screen.getByText("Checking your session…")).toBeInTheDocument()
    expect(screen.queryByText(/signed in as/)).not.toBeInTheDocument()
    resolveSession(signedInUser)
    expect(
      await screen.findByText(`signed in as ${signedInUser.email}`),
    ).toBeInTheDocument()
  })

  it("clears auth state only after the server logout succeeds", async () => {
    const user = userEvent.setup()
    render(
      <AuthProvider>
        <AuthStateHarness />
      </AuthProvider>,
    )
    expect(
      await screen.findByText(`signed in as ${signedInUser.email}`),
    ).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Sign out test" }))
    expect(await screen.findByText("signed out")).toBeInTheDocument()
    expect(authApi.logout).toHaveBeenCalledOnce()
  })

  it("keeps the authenticated state if the server cannot revoke a logout session", async () => {
    authApi.logout.mockRejectedValueOnce(new Error("network"))
    render(
      <AuthProvider>
        <AuthStateHarness />
      </AuthProvider>,
    )
    expect(
      await screen.findByText(`signed in as ${signedInUser.email}`),
    ).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Sign out test" }))
    await waitFor(() => expect(authApi.logout).toHaveBeenCalledOnce())
    expect(
      screen.getByText(`signed in as ${signedInUser.email}`),
    ).toBeInTheDocument()
  })

  it("shows the session-expired message after a later 401 refresh failure", async () => {
    render(
      <AuthProvider>
        <AuthStateHarness />
      </AuthProvider>,
    )
    expect(
      await screen.findByText(`signed in as ${signedInUser.email}`),
    ).toBeInTheDocument()
    window.dispatchEvent(new Event("cognate-auth-expired"))
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Your session has expired. Please sign in again.",
    )
    expect(screen.getByText("signed out")).toBeInTheDocument()
  })

  it("turns an API 403 event into the access-restricted page state", async () => {
    render(
      <AuthProvider>
        <AuthStateHarness />
      </AuthProvider>,
    )
    expect(
      await screen.findByText(`signed in as ${signedInUser.email}`),
    ).toBeInTheDocument()
    window.dispatchEvent(new CustomEvent("cognate-access-restricted"))
    expect(
      await screen.findByRole("heading", { name: "Access restricted" }),
    ).toBeInTheDocument()
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
  })

  it("invokes the login callback on success and maps a 401 to the generic credential message", async () => {
    const user = userEvent.setup()
    const onAuthenticated = vi.fn()
    authApi.fetchCurrentUser.mockRejectedValue(
      new authApi.ApiError(401, "expired"),
    )
    authApi.login.mockResolvedValue(signedInUser)
    const firstLogin = render(
      <AuthProvider>
        <LoginPage onAuthenticated={onAuthenticated} />
      </AuthProvider>,
    )
    await screen.findByLabelText("Email")
    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: signedInUser.email },
    })
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "synthetic secret phrase" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Sign In" }))
    await waitFor(() => expect(onAuthenticated).toHaveBeenCalledOnce())
    expect(authApi.login).toHaveBeenCalledWith(
      signedInUser.email,
      "synthetic secret phrase",
      false,
    )

    firstLogin.unmount()
    authApi.login.mockRejectedValueOnce(
      new authApi.ApiError(401, "wrong credential details"),
    )
    render(
      <AuthProvider>
        <LoginPage onAuthenticated={vi.fn()} />
      </AuthProvider>,
    )
    await screen.findByLabelText("Email")
    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: signedInUser.email },
    })
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "incorrect synthetic phrase" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Sign In" }))
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Invalid email or password.",
    )
  })

  it("uses the backend remember-me option and displays forbidden login as an access-restricted state", async () => {
    const user = userEvent.setup()
    authApi.fetchCurrentUser.mockRejectedValue(
      new authApi.ApiError(401, "unauthenticated"),
    )
    authApi.login.mockRejectedValue(new authApi.ApiError(403, "forbidden"))
    render(
      <AuthProvider>
        <LoginPage onAuthenticated={vi.fn()} />
      </AuthProvider>,
    )
    await screen.findByLabelText("Email")
    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: signedInUser.email },
    })
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "synthetic secret phrase" },
    })
    fireEvent.click(screen.getByRole("checkbox", { name: "Remember me" }))
    fireEvent.click(screen.getByRole("button", { name: "Sign In" }))
    expect(authApi.login).toHaveBeenCalledWith(
      signedInUser.email,
      "synthetic secret phrase",
      true,
    )
    expect(
      await screen.findByRole("heading", { name: "Access restricted" }),
    ).toBeInTheDocument()
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
  })

  it("requires a valid email and a password before enabling a sign-in request", async () => {
    authApi.fetchCurrentUser.mockRejectedValue(
      new authApi.ApiError(401, "unauthenticated"),
    )
    render(
      <AuthProvider>
        <LoginPage onAuthenticated={vi.fn()} />
      </AuthProvider>,
    )
    expect(await screen.findByLabelText("Email")).toBeRequired()
    expect(screen.getByLabelText("Email")).toHaveAttribute("type", "email")
    expect(screen.getByLabelText("Password")).toBeRequired()
    expect(screen.getByRole("button", { name: "Sign In" })).toBeEnabled()
  })

  it("redirects protected routes after loading and shows a role-restricted state", async () => {
    const onUnauthenticated = vi.fn()
    const { rerender } = render(
      <ProtectedRoute
        isLoading
        onUnauthenticated={onUnauthenticated}
        isAuthenticated={false}
      >
        <div>Protected patient records</div>
      </ProtectedRoute>,
    )
    expect(screen.getByText("Checking your session…")).toBeInTheDocument()
    expect(
      screen.queryByText("Protected patient records"),
    ).not.toBeInTheDocument()
    rerender(
      <ProtectedRoute
        isLoading={false}
        onUnauthenticated={onUnauthenticated}
        isAuthenticated={false}
      >
        <div>Protected patient records</div>
      </ProtectedRoute>,
    )
    await waitFor(() => expect(onUnauthenticated).toHaveBeenCalledOnce())
    expect(
      screen.queryByText("Protected patient records"),
    ).not.toBeInTheDocument()

    render(
      <RoleRoute user={signedInUser} allowedRoles={["admin", "operator"]}>
        <div>Operations data</div>
      </RoleRoute>,
    )
    expect(
      screen.getByRole("heading", { name: "Access restricted" }),
    ).toBeInTheDocument()
    expect(screen.queryByText("Operations data")).not.toBeInTheDocument()
  })

  it("rejects external and protocol-relative return destinations", () => {
    expect(safeReturnPath("/documents?page=2", "https://mdis.example")).toBe(
      "/documents?page=2",
    )
    expect(
      safeReturnPath("https://attacker.example", "https://mdis.example"),
    ).toBe("/dashboard")
    expect(
      safeReturnPath("//attacker.example/path", "https://mdis.example"),
    ).toBe("/dashboard")
    expect(safeReturnPath("/\\attacker.example", "https://mdis.example")).toBe(
      "/dashboard",
    )
  })

  it("renders the server 403 state as a page, not an error banner", () => {
    render(<AccessRestrictedState />)
    expect(
      screen.getByRole("heading", { name: "Access restricted" }),
    ).toBeInTheDocument()
    expect(
      screen.getByText("You don't have permission to access this resource."),
    ).toBeInTheDocument()
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
  })

  it("warns before the configured inactivity timeout and can refresh the session", async () => {
    vi.useFakeTimers()
    vi.stubEnv("VITE_AUTH_INACTIVITY_MINUTES", "1")
    render(
      <AuthProvider>
        <AuthStateHarness />
      </AuthProvider>,
    )
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })
    expect(screen.getByText(/signed in as/)).toBeInTheDocument()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(58_000)
    })
    expect(screen.getByRole("alertdialog")).toHaveTextContent(
      "You will be signed out soon due to inactivity.",
    )
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Stay signed in" }))
      await Promise.resolve()
    })
    expect(authApi.refreshAuthSession).toHaveBeenCalledOnce()
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument()
    vi.useRealTimers()
    vi.unstubAllEnvs()
  })

  it.each([
    ["pending_email_verification", "Verify your email"],
    ["pending_approval", "Approval pending"],
    ["rejected", "Account request not approved"],
  ])("shows the account status page for %s", async (status, heading) => {
    authApi.fetchCurrentUser.mockRejectedValue(
      new authApi.ApiError(401, "unauthenticated"),
    )
    authApi.login.mockRejectedValueOnce(
      new authApi.ApiError(202, "account status", {
        status,
        rejection_reason:
          status === "rejected" ? "Synthetic review reason" : null,
      }),
    )
    render(
      <AuthProvider>
        <LoginPage onAuthenticated={vi.fn()} />
      </AuthProvider>,
    )
    await screen.findByLabelText("Email")
    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: signedInUser.email },
    })
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "synthetic secret phrase" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Sign In" }))
    expect(
      await screen.findByRole("heading", { name: heading }),
    ).toBeInTheDocument()
    if (status === "rejected") {
      expect(screen.getByRole("status")).toHaveTextContent(
        "Synthetic review reason",
      )
    }
    expect(screen.queryByLabelText("Password")).not.toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: "Back to sign in" }),
    ).toBeInTheDocument()
  })
})
