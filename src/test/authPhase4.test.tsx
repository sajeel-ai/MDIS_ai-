import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

const api = vi.hoisted(() => ({
  requestPasswordReset: vi.fn(),
  verifyResetCode: vi.fn(),
  verifyRegistrationEmail: vi.fn(),
  resendVerificationEmail: vi.fn(),
  fetchAccountRequests: vi.fn(),
  approveAccountRequest: vi.fn(),
  rejectAccountRequest: vi.fn(),
  resetPassword: vi.fn(),
  acceptInvitation: vi.fn(),
  changePassword: vi.fn(),
  enableMfa: vi.fn(),
  fetchAuthConfig: vi.fn(),
  selfRegister: vi.fn(),
  fetchManagedUsers: vi.fn(),
  fetchManagedSessions: vi.fn(),
  inviteManagedUser: vi.fn(),
  updateManagedUserRole: vi.fn(),
  setManagedUserActive: vi.fn(),
  revokeManagedSession: vi.fn(),
  beginMfaSetup: vi.fn(),
  login: vi.fn(),
}))

vi.mock("../services/api", () => ({
  ...api,
  ApiError: class ApiError extends Error {
    constructor(
      readonly status: number,
      message: string,
    ) {
      super(message)
    }
  },
}))
vi.mock("../auth/AuthProvider", () => ({
  useAuth: () => ({ beginMfaSetup: api.beginMfaSetup, login: api.login }),
}))
vi.mock("../layouts/AppLayout", () => ({
  AppLayout: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
}))

import {
  AcceptInvitationPage,
  ChangePasswordPage,
  ForgotPasswordPage,
  ForbiddenPage,
  MfaSetupPage,
  MfaVerifyPage,
  RegisterPage,
  ResetPasswordPage,
  SessionExpiredPage,
} from "../pages/AuthFlows"
import { AdminUsersPage } from "../pages/AdminUsers"
import { RoleRoute } from "../auth/RouteGuards"
import { ApiError } from "../services/api"

describe("Phase 4 authentication pages", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.requestPasswordReset.mockResolvedValue({
      message: "If the account exists, an email has been sent",
    })
    api.resetPassword.mockResolvedValue({
      message: "Password has been reset. Sign in again.",
    })
    api.acceptInvitation.mockResolvedValue({
      status: "accepted",
      message: "Invitation accepted. Sign in to continue.",
    })
    api.changePassword.mockResolvedValue({
      message: "Password changed. Sign in again.",
    })
    api.enableMfa.mockResolvedValue(["recovery-code"])
    api.beginMfaSetup.mockResolvedValue("otpauth://totp/synthetic")
    api.login.mockResolvedValue({
      id: "user",
      email: "user@example.test",
      display_name: null,
      role: "clinician",
    })
    api.fetchAuthConfig.mockResolvedValue({ self_registration_enabled: false })
    api.fetchAuthConfig.mockResolvedValue({
      registration_mode: "disabled",
      self_registration_enabled: false,
      organizations: [],
    })
    api.selfRegister.mockResolvedValue({ message: "Pending approval" })
    api.verifyResetCode.mockResolvedValue({
      grant: "synthetic-reset-grant",
      expires_in: 900,
    })
    api.verifyRegistrationEmail.mockResolvedValue({
      status: "pending_approval",
      message:
        "Email verified. Your account is awaiting organization approval.",
    })
    api.resendVerificationEmail.mockResolvedValue({
      message: "If the account exists, we sent a code.",
    })
    api.fetchAccountRequests.mockResolvedValue([])
    api.approveAccountRequest.mockResolvedValue({
      status: "approved",
      email_delivery: "queued",
    })
    api.rejectAccountRequest.mockResolvedValue({
      status: "rejected",
      email_delivery: "not_configured",
    })
    api.fetchManagedUsers.mockResolvedValue([
      {
        id: "user-1",
        email: "person@example.test",
        full_name: "Synthetic Person",
        role: "clinician",
        is_active: true,
        pending_approval: false,
        mfa_enabled: false,
      },
    ])
    api.fetchManagedSessions.mockResolvedValue([
      {
        family_id: "family-1",
        created_at: "2026-10-05T00:00:00Z",
        expires_at: "2026-10-06T00:00:00Z",
      },
    ])
    api.inviteManagedUser.mockResolvedValue({
      status: "invited",
      email_delivery: "not_configured",
    })
    api.updateManagedUserRole.mockResolvedValue({
      status: "updated",
      role: "viewer",
    })
    api.setManagedUserActive.mockResolvedValue({ status: "deactivated" })
    api.revokeManagedSession.mockResolvedValue({ status: "revoked" })
  })

  it("renders recovery, expired, forbidden, and MFA verification screens accessibly", () => {
    const { rerender } = render(<ForgotPasswordPage />)
    expect(
      screen.getByRole("heading", { name: "Reset your password" }),
    ).toBeInTheDocument()
    expect(screen.getByLabelText("Email")).toHaveAttribute(
      "autocomplete",
      "email",
    )
    rerender(<SessionExpiredPage />)
    expect(
      screen.getByText("Your session has expired. Please sign in again."),
    ).toBeInTheDocument()
    rerender(<ForbiddenPage />)
    expect(
      screen.getByRole("heading", { name: "Access restricted" }),
    ).toBeInTheDocument()
    rerender(<MfaVerifyPage onAuthenticated={vi.fn()} />)
    expect(
      screen.getByLabelText("Authenticator or recovery code"),
    ).toHaveAttribute("autocomplete", "one-time-code")
  })

  it("submits generic reset requests without account enumeration", async () => {
    const user = userEvent.setup()
    render(<ForgotPasswordPage />)
    await user.type(screen.getByLabelText("Email"), "person@example.test")
    await user.click(
      screen.getByRole("button", { name: "Send reset instructions" }),
    )
    expect(await screen.findByRole("status")).toHaveTextContent(
      "If the account exists",
    )
  })

  it("explains when reset email delivery is not configured", async () => {
    api.requestPasswordReset.mockRejectedValueOnce(
      new ApiError(503, "Email delivery is not configured"),
    )
    const user = userEvent.setup()
    render(<ForgotPasswordPage />)
    await user.type(screen.getByLabelText("Email"), "person@example.test")
    await user.click(
      screen.getByRole("button", { name: "Send reset instructions" }),
    )
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Email delivery is not configured",
    )
  })

  it("verifies MFA using the existing cookie-auth login provider", async () => {
    const complete = vi.fn()
    const user = userEvent.setup()
    render(<MfaVerifyPage onAuthenticated={complete} />)
    await user.type(
      screen.getByLabelText("Authenticator or recovery code"),
      "123456",
    )
    await user.click(screen.getByRole("button", { name: "Verify and sign in" }))
    await waitFor(() =>
      expect(api.login).toHaveBeenCalledWith("", "", false, "123456"),
    )
    expect(complete).toHaveBeenCalledOnce()
  })

  it("verifies a reset code, validates matching passwords, then submits the grant flow", async () => {
    const user = userEvent.setup()
    render(<ResetPasswordPage />)
    await user.type(screen.getByLabelText("Email"), "person@example.test")
    await user.click(screen.getByRole("button", { name: "Send reset code" }))
    await user.type(await screen.findByLabelText("Verification code"), "123456")
    await user.click(screen.getByRole("button", { name: "Verify code" }))
    await user.type(
      screen.getByLabelText("New password"),
      "synthetic new password 1",
    )
    await user.type(
      screen.getByLabelText("Confirm new password"),
      "different password",
    )
    await user.click(
      screen.getByRole("button", {
        name: "Reset password",
      }),
    )
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Passwords do not match.",
    )
    await user.clear(screen.getByLabelText("Confirm new password"))
    await user.type(
      screen.getByLabelText("Confirm new password"),
      "synthetic new password 1",
    )
    await user.click(
      screen.getByRole("button", {
        name: "Reset password",
      }),
    )
    await waitFor(() =>
      expect(api.verifyResetCode).toHaveBeenCalledWith(
        "person@example.test",
        "123456",
      ),
    )
    expect(api.resetPassword).toHaveBeenCalledWith(
      "synthetic-reset-grant",
      "synthetic new password 1",
    )
    expect(
      await screen.findByText(/password has been reset/i),
    ).toBeInTheDocument()
  })

  it("accepts invitations through the single-use invite token", async () => {
    window.history.replaceState(
      null,
      "",
      "/?token=synthetic-invite-token-123456789",
    )
    const user = userEvent.setup()
    render(<AcceptInvitationPage />)
    await user.type(
      screen.getByLabelText("New password"),
      "synthetic new password 1",
    )
    await user.type(
      screen.getByLabelText("Confirm new password"),
      "synthetic new password 1",
    )
    await user.click(screen.getByRole("button", { name: "Accept invitation" }))
    await waitFor(() =>
      expect(api.acceptInvitation).toHaveBeenCalledWith(
        "synthetic-invite-token-123456789",
        "synthetic new password 1",
      ),
    )
  })

  it("changes password and ends the local session only after server success", async () => {
    const done = vi.fn()
    const user = userEvent.setup()
    render(<ChangePasswordPage onDone={done} />)
    await user.type(screen.getByLabelText("Current password"), "old password")
    await user.type(
      screen.getByLabelText("New password"),
      "synthetic new password 1",
    )
    await user.type(
      screen.getByLabelText("Confirm new password"),
      "synthetic new password 1",
    )
    await user.click(screen.getByRole("button", { name: "Change password" }))
    await waitFor(() => expect(done).toHaveBeenCalledOnce())
    expect(api.changePassword).toHaveBeenCalledWith(
      "old password",
      "synthetic new password 1",
    )
  })

  it("runs MFA enrollment and exposes one-time recovery codes to the completion handler", async () => {
    const complete = vi.fn()
    const user = userEvent.setup()
    render(<MfaSetupPage onComplete={complete} />)
    await user.click(screen.getByRole("button", { name: "Get setup value" }))
    expect(await screen.findByLabelText("Manual setup value")).toHaveValue(
      "synthetic",
    )
    expect(screen.getByTitle("Authenticator setup QR code")).toBeInTheDocument()
    await user.type(screen.getByLabelText("Authenticator code"), "123456")
    await user.click(screen.getByRole("button", { name: "Enable MFA" }))
    await waitFor(() =>
      expect(complete).toHaveBeenCalledWith(["recovery-code"]),
    )
  })

  it("keeps public registration hidden unless backend configuration enables it", async () => {
    const { unmount } = render(<RegisterPage />)
    expect(
      await screen.findByRole("heading", { name: "Registration unavailable" }),
    ).toBeInTheDocument()
    api.fetchAuthConfig.mockResolvedValueOnce({
      registration_mode: "approval",
      self_registration_enabled: true,
      organizations: [{ id: "org-1", name: "Synthetic Clinic" }],
    })
    unmount()
    render(<RegisterPage />)
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: "Request an account" }),
      ).toBeInTheDocument(),
    )
    const user = userEvent.setup()
    await user.type(screen.getByLabelText("Full name"), "Synthetic Clinician")
    await user.type(screen.getByLabelText("Email"), "new@example.test")
    await user.type(
      screen.getByLabelText("New password"),
      "synthetic registration password",
    )
    await user.type(
      screen.getByLabelText("Confirm new password"),
      "synthetic registration password",
    )
    await user.click(
      screen.getByRole("checkbox", {
        name: "I accept the account registration terms.",
      }),
    )
    await user.click(screen.getByRole("button", { name: "Request account" }))
    await waitFor(() =>
      expect(api.selfRegister).toHaveBeenCalledWith(
        expect.objectContaining({
          work_email: "new@example.test",
          organization_id: "org-1",
          professional_role: "doctor",
          confirm_password: "synthetic registration password",
          accepted_terms: true,
        }),
      ),
    )
    expect(
      await screen.findByRole("heading", { name: "Verify your email" }),
    ).toBeInTheDocument()
    await user.type(screen.getByLabelText("Verification code"), "123456")
    await user.click(screen.getByRole("button", { name: "Verify email" }))
    expect(
      await screen.findByRole("heading", { name: "Email verified" }),
    ).toBeInTheDocument()
    expect(api.verifyRegistrationEmail).toHaveBeenCalledWith(
      "new@example.test",
      "123456",
    )
  })

  it("provides organization user actions and denies the screen to a clinician", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true)
    const user = userEvent.setup()
    const { container } = render(<AdminUsersPage onNavigate={vi.fn()} />)
    expect(
      await screen.findByRole("heading", { name: "User Management" }),
    ).toBeInTheDocument()
    expect(await screen.findByText("person@example.test")).toBeInTheDocument()
    expect(container.querySelector("table")?.parentElement).toHaveClass(
      "overflow-x-auto",
    )
    await user.click(screen.getByRole("button", { name: "Sessions" }))
    expect(await screen.findByText(/Active sessions:/)).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Revoke session" }))
    expect(confirm).toHaveBeenCalled()
    expect(api.revokeManagedSession).toHaveBeenCalledWith("user-1", "family-1")
    await user.type(screen.getByLabelText("Full name"), "New Synthetic User")
    await user.type(screen.getByLabelText("Email"), "new@example.test")
    await user.click(screen.getByRole("button", { name: "Send invitation" }))
    expect(await screen.findByRole("status")).toHaveTextContent(
      "email delivery not configured",
    )
    await user.selectOptions(
      screen.getByLabelText("Role for person@example.test"),
      "viewer",
    )
    await waitFor(() =>
      expect(api.updateManagedUserRole).toHaveBeenCalledWith(
        "user-1",
        "viewer",
      ),
    )
    await user.click(screen.getByRole("button", { name: "Deactivate" }))
    await waitFor(() =>
      expect(api.setManagedUserActive).toHaveBeenCalledWith("user-1", false),
    )
    const { rerender } = render(
      <RoleRoute
        user={{
          id: "u",
          email: "c@example.test",
          role: "clinician",
          display_name: null,
        }}
        allowedRoles={["admin"]}
      >
        <AdminUsersPage onNavigate={vi.fn()} />
      </RoleRoute>,
    )
    rerender(
      <RoleRoute
        user={{
          id: "u",
          email: "c@example.test",
          role: "clinician",
          display_name: null,
        }}
        allowedRoles={["admin"]}
      >
        <AdminUsersPage onNavigate={vi.fn()} />
      </RoleRoute>,
    )
    expect(
      screen.getByRole("heading", { name: "Access restricted" }),
    ).toBeInTheDocument()
    expect(api.fetchManagedUsers.mock.calls.length).toBeGreaterThanOrEqual(4)
    confirm.mockRestore()
  })

  it("shows when an invitation has been queued for delivery", async () => {
    const user = userEvent.setup()
    api.inviteManagedUser.mockResolvedValueOnce({
      status: "invited",
      email_delivery: "queued",
    })
    render(<AdminUsersPage onNavigate={vi.fn()} />)
    await user.type(
      await screen.findByLabelText("Full name"),
      "Synthetic Invitee",
    )
    await user.type(screen.getByLabelText("Email"), "invitee@example.test")
    await user.click(screen.getByRole("button", { name: "Send invitation" }))
    expect(await screen.findByRole("status")).toHaveTextContent(
      "Invitation queued for delivery",
    )
  })

  it("lets an administrator approve verified account requests with a role", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true)
    api.fetchAccountRequests.mockResolvedValueOnce([
      {
        id: "request-1",
        email: "applicant@example.test",
        full_name: "Synthetic Applicant",
        professional_role_requested: "doctor",
        license_or_certification_number: null,
        license_type: null,
        requested_organization_name: null,
        created_at: "2026-10-07T00:00:00Z",
      },
    ])
    const user = userEvent.setup()
    render(<AdminUsersPage onNavigate={vi.fn()} />)
    expect(
      await screen.findByLabelText("Role for applicant@example.test"),
    ).toBeInTheDocument()
    await user.selectOptions(
      screen.getByLabelText("Role for applicant@example.test"),
      "reviewer",
    )
    await user.click(screen.getByRole("button", { name: "Approve" }))
    await waitFor(() =>
      expect(api.approveAccountRequest).toHaveBeenCalledWith(
        "request-1",
        "reviewer",
      ),
    )
    expect(await screen.findByRole("status")).toHaveTextContent(
      "Account approved and notification queued",
    )
  })
})
