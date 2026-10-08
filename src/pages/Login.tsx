import { useEffect, useState, type FormEvent } from "react"
import {
  ArrowRight,
  CheckCircle2,
  Eye,
  EyeOff,
  FileText,
  LockKeyhole,
  Mail,
  SearchCheck,
  ShieldCheck,
} from "lucide-react"
import mdisMarkUrl from "../public/Glossy Blue Ribbon M Emblem.png"
import {
  ApiError,
  fetchAuthConfig,
  requestPasswordReset,
} from "../services/api"
import { authErrorMessage, useAuth } from "../auth/AuthProvider"

type LoginMode = "credentials" | "mfa_verify" | "mfa_setup" | "forgot" | "restricted" | "account_status"

export function LoginPage({
  onAuthenticated,
  onResetRequested,
}: {
  onAuthenticated: (recoveryCodes?: string[]) => void
  onResetRequested?: (email: string) => void
}) {
  const { login, beginMfaSetup, enableMfa, authError: sessionError } = useAuth()
  const [mode, setMode] = useState<LoginMode>("credentials")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [rememberMe, setRememberMe] = useState(false)
  const [code, setCode] = useState("")
  const [provisioningUri, setProvisioningUri] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [registrationEnabled, setRegistrationEnabled] = useState(false)
  const [accountStatus, setAccountStatus] = useState<{
    title: string
    message: string
  } | null>(null)

  useEffect(() => {
    let active = true
    void fetchAuthConfig()
      .then((config) => {
        if (active) setRegistrationEnabled(config.self_registration_enabled)
      })
      .catch(() => undefined)
    return () => {
      active = false
    }
  }, [])

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (busy) return
    setError(null)
    setBusy(true)
    try {
      if (mode === "forgot") {
        await requestPasswordReset(email)
        if (onResetRequested) onResetRequested(email)
        else window.location.assign("/reset-password?step=code")
        return
      }
      if (mode === "mfa_setup") {
        const recoveryCodes = await enableMfa(code)
        setPassword("")
        onAuthenticated(recoveryCodes)
        return
      }
      await login(
        email,
        password,
        rememberMe,
        mode === "mfa_verify" ? code : undefined,
      )
      setPassword("")
      onAuthenticated()
    } catch (caught) {
      if (
        caught instanceof ApiError &&
        caught.status === 202 &&
        caught.message.includes("MFA verification required")
      ) {
        setMode("mfa_verify")
        return
      }
      if (
        caught instanceof ApiError &&
        caught.status === 403 &&
        mode === "credentials" &&
        caught.message.includes("MFA enrollment required")
      ) {
        setMode("mfa_setup")
        try {
          setProvisioningUri(await beginMfaSetup())
        } catch (setupError) {
          setError(authErrorMessage(setupError))
        }
        return
      }
      if (
        caught instanceof ApiError &&
        caught.status === 403 &&
        mode === "credentials" &&
        caught.message.includes("MFA verification required")
      ) {
        setMode("mfa_verify")
        return
      }
      if (caught instanceof ApiError && caught.status === 202) {
        const data = caught.data as {
          status?: string
          rejection_reason?: string | null
        } | undefined
        const states: Record<string, { title: string; message: string }> = {
          pending_email_verification: {
            title: "Verify your email",
            message:
              "Your account request is not complete. Use the verification code sent to your email, then sign in again.",
          },
          pending_approval: {
            title: "Approval pending",
            message:
              "Your email is verified. Your organization must approve your account before you can sign in.",
          },
          rejected: {
            title: "Account request not approved",
            message:
              data?.rejection_reason ||
              "Your organization did not approve this account request. Contact your organization for more information.",
          },
        }
        const state = data?.status ? states[data.status] : undefined
        if (state) {
          setAccountStatus(state)
          setMode("account_status")
        } else {
          setError(caught.message.replace(/^API 202: /, ""))
        }
        return
      }
      if (caught instanceof ApiError && caught.status === 403) {
        setMode("restricted")
        return
      }
      if (
        mode === "mfa_verify" &&
        caught instanceof ApiError &&
        caught.status === 401
      ) {
        setError("Invalid authenticator or recovery code.")
      } else if (mode === "forgot") {
        setError(
          caught instanceof ApiError && caught.status === 503
            ? "Email delivery is not configured. Contact your administrator."
            : "Unable to connect to the authentication service.",
        )
      } else {
        setError(authErrorMessage(caught))
      }
    } finally {
      setBusy(false)
    }
  }

  const title =
    mode === "forgot"
      ? "Reset your password"
      : mode === "mfa_setup"
        ? "Secure your account"
        : mode === "mfa_verify"
          ? "Verify your identity"
          : mode === "account_status"
            ? (accountStatus?.title ?? "Account status")
            : "Welcome back"
  const subtitle =
    mode === "forgot"
      ? "Enter your account email and we will send reset instructions if the account exists."
      : mode === "mfa_setup"
        ? "Add this account to an authenticator app, then enter its current code."
        : mode === "mfa_verify"
          ? "Enter an authenticator code or a one-time recovery code."
          : mode === "account_status"
            ? "Your account cannot sign in yet."
            : "Sign in to your MDIS workspace."

  if (mode === "restricted") {
    return (
      <main className="flex min-h-screen items-center justify-center bg-[#EAF5FF] px-5 py-10">
        <section className="w-full max-w-lg rounded-3xl border border-[#DCE7F3] bg-white p-8 text-center shadow-[0_20px_60px_rgba(7,26,61,0.08)] sm:p-10">
          <img src={mdisMarkUrl} alt="" className="mx-auto mb-5 h-16 w-16 object-contain" />
          <h1 className="text-2xl font-semibold text-[#071A3D]">Access restricted</h1>
          <p className="mt-2 text-sm text-[#52627A]">
            You don't have permission to access this resource.
          </p>
        </section>
      </main>
    )
  }

  return (
    <main className="min-h-screen bg-[#EAF5FF] lg:grid lg:grid-cols-2">
      <section className="relative hidden min-h-screen overflow-x-hidden overflow-y-auto bg-[radial-gradient(ellipse_at_85%_105%,#087BFF_0%,transparent_42%),linear-gradient(135deg,#06183A_0%,#08285C_56%,#0649A8_100%)] px-10 py-8 text-white lg:flex lg:h-screen lg:min-h-0 lg:flex-col lg:justify-between xl:px-14 xl:py-10">
        <div className="absolute inset-0 overflow-hidden" aria-hidden="true">
          <div className="absolute -right-28 -top-28 h-[30rem] w-[30rem] rounded-full border border-[#1688FF]/35" />
          <div className="absolute -right-12 -top-12 h-[24rem] w-[24rem] rounded-full border border-[#1688FF]/35" />
          <div className="absolute -bottom-48 -left-28 h-[27rem] w-[65rem] rotate-[-12deg] rounded-[50%] border border-[#16C7E8]/25 bg-gradient-to-r from-transparent via-[#146EF5]/15 to-[#146EF5]/50" />
          <div className="absolute bottom-16 left-0 h-px w-[70%] bg-gradient-to-r from-[#16C7E8]/50 to-transparent" />
        </div>
        <div className="relative z-10 my-auto max-w-2xl py-6">
          <div className="mb-6 flex items-center gap-3">
            <img src={mdisMarkUrl} alt="" className="h-10 w-10 object-contain" />
          </div>
          <div className="mb-5 flex items-center gap-4 text-[11px] font-medium uppercase tracking-[0.16em] text-[#C4D4F4]">
            <span className="h-0.5 w-9 bg-[#16C7E8]" />
            Medical Document Intelligence System
          </div>
          <h1 className="max-w-xl text-3xl font-semibold leading-[1.18] tracking-[-0.02em] xl:text-[38px]">
            Turn medical documents into <span className="text-[#16C7E8]">clinical intelligence.</span>
          </h1>
          <p className="mt-5 max-w-xl text-[15px] leading-6 text-[#DCE7F3]">
            Extract, verify, normalize and review clinical information with an evidence-grounded AI workflow.
          </p>
          <div className="mt-8 grid max-w-2xl grid-cols-[1fr_auto_1fr_auto_1fr] items-start gap-2">
            <div className="min-w-0">
              <div className="grid h-20 w-full max-w-36 place-items-center rounded-2xl border border-[#37A4FF]/30 bg-white/[0.06] text-[#16C7E8]">
                <FileText size={34} strokeWidth={1.7} />
              </div>
              <p className="mt-3 text-xs font-semibold uppercase tracking-[0.16em]">AI Extraction</p>
              <p className="mt-2 max-w-36 text-xs leading-5 text-[#C4D4F4]">Extracts key clinical information.</p>
            </div>
            <ArrowRight className="mt-8 text-[#16C7E8]" size={20} aria-hidden="true" />
            <div className="min-w-0">
              <div className="grid h-20 w-full max-w-36 place-items-center rounded-2xl border border-[#37A4FF]/30 bg-white/[0.06] text-[#16C7E8]">
                <SearchCheck size={34} strokeWidth={1.7} />
              </div>
              <p className="mt-3 text-xs font-semibold uppercase tracking-[0.16em]">Clinic Review</p>
              <p className="mt-2 max-w-36 text-xs leading-5 text-[#C4D4F4]">Clinic reviewers validate and approve.</p>
            </div>
            <ArrowRight className="mt-8 text-[#16C7E8]" size={20} aria-hidden="true" />
            <div className="min-w-0">
              <div className="grid h-20 w-full max-w-36 place-items-center rounded-2xl border border-[#37A4FF]/30 bg-white/[0.06] text-[#16C7E8]">
                <CheckCircle2 size={34} strokeWidth={1.7} />
              </div>
              <p className="mt-3 text-xs font-semibold uppercase tracking-[0.16em]">Approved Data</p>
              <p className="mt-2 max-w-36 text-xs leading-5 text-[#C4D4F4]">Structured, normalized data ready for use.</p>
            </div>
          </div>
        </div>
        <p className="relative z-10 flex items-center gap-4 text-sm text-[#C4D4F4]">
          <span className="h-0.5 w-9 bg-[#16C7E8]" />
          AI-assisted extraction. Human-approved results.
        </p>
      </section>

      <section className="relative flex min-h-screen items-center justify-center overscroll-y-contain overflow-x-hidden overflow-y-auto bg-[radial-gradient(ellipse_at_100%_0%,#D8EEFF_0%,transparent_36%),radial-gradient(ellipse_at_0%_100%,#D8EEFF_0%,transparent_34%),#F5FAFF] px-4 py-8 sm:px-8 sm:py-12 lg:h-screen lg:min-h-0">
        <div className="pointer-events-none absolute -right-36 top-[-7rem] h-[32rem] w-[32rem] rounded-full border-[3rem] border-[#D8EEFF]/50" aria-hidden="true" />
        <div className="relative my-auto w-full max-w-[520px]">
          <form
            onSubmit={submit}
            className="rounded-[24px] border border-[#DCE7F3] bg-white/95 px-6 py-7 shadow-[0_18px_55px_rgba(20,110,245,0.11)] sm:px-10 sm:py-9 lg:px-12 lg:py-10"
          >
            <div className="mb-7 flex items-center justify-center">
              <img src={mdisMarkUrl} alt="MDIS" className="h-12 w-12 shrink-0 object-contain sm:h-14 sm:w-14" />
            </div>
            <h2 className="text-[27px] font-semibold leading-tight tracking-[-0.02em] text-[#071A3D] sm:text-[30px]">{title}</h2>
            <p className="mt-2 text-[15px] leading-6 text-[#52627A]">{subtitle}</p>

            {sessionError && (
              <p
                role="alert"
                className="mt-5 rounded-lg border border-[#DCE7F3] bg-[#EAF5FF] p-3 text-sm text-[#071A3D]"
              >
                {sessionError}
              </p>
            )}
            {error && (
              <p
                role="alert"
                className="mt-5 rounded-lg border border-[#FECACA] bg-[#FEF2F2] p-3 text-sm text-[#B91C1C]"
              >
                {error}
              </p>
            )}
            {mode === "account_status" && (
              <div
                role="status"
                className="mt-5 rounded-lg border border-[#DCE7F3] bg-[#EAF5FF] p-3 text-sm text-[#071A3D]"
              >
                {accountStatus?.message}
              </div>
            )}

            {mode !== "mfa_setup" &&
              mode !== "mfa_verify" &&
              mode !== "account_status" && (
                <label className="mt-7 block text-sm font-semibold text-[#071A3D]">
                  Email
                  <span className="relative mt-2 block">
                    <Mail size={18} aria-hidden="true" className="absolute left-4 top-1/2 -translate-y-1/2 text-[#7184B4]" />
                    <input
                      autoComplete="username"
                      type="email"
                      required
                      maxLength={256}
                      value={email}
                      onChange={(event) => setEmail(event.target.value)}
                      placeholder="you@organization.com"
                      className="h-[54px] w-full rounded-xl border border-[#DCE7F3] bg-white pl-14 pr-4 text-[15px] font-normal text-[#071A3D] outline-none placeholder:text-[#8292BC] focus:border-[#146EF5] focus:ring-2 focus:ring-[#146EF5]/15"
                    />
                  </span>
                </label>
              )}

            {mode === "credentials" && (
              <label className="mt-6 block text-sm font-semibold text-[#071A3D]">
                Password
                <span className="relative mt-2 block">
                  <LockKeyhole size={18} aria-hidden="true" className="absolute left-4 top-1/2 -translate-y-1/2 text-[#7184B4]" />
                  <input
                    autoComplete="current-password"
                    type={showPassword ? "text" : "password"}
                    required
                    maxLength={1024}
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    placeholder="Enter your password"
                    className="h-[54px] w-full rounded-xl border border-[#DCE7F3] bg-white pl-14 pr-14 text-[15px] font-normal text-[#071A3D] outline-none placeholder:text-[#8292BC] focus:border-[#146EF5] focus:ring-2 focus:ring-[#146EF5]/15"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((value) => !value)}
                    aria-label={
                      showPassword ? "Hide password" : "Show password"
                    }
                    className="absolute inset-y-0 right-2 grid w-11 place-items-center rounded-lg text-[#7184B4] hover:text-[#146EF5] focus-visible:outline-2 focus-visible:outline-[#146EF5]"
                  >
                    {showPassword ? (
                      <EyeOff size={18} aria-hidden="true" />
                    ) : (
                      <Eye size={18} aria-hidden="true" />
                    )}
                  </button>
                </span>
              </label>
            )}

            {mode === "mfa_setup" && provisioningUri && (
              <div className="mt-6 rounded-lg border border-[#DCE7F3] bg-[#F5FAFF] p-3 text-xs text-[#52627A]">
                <span className="mb-1 block font-semibold text-[#071A3D]">
                  Authenticator setup value
                </span>
                <span className="break-all">{provisioningUri}</span>
              </div>
            )}
            {(mode === "mfa_setup" || mode === "mfa_verify") && (
              <label className="mt-5 block text-sm font-medium text-[#071A3D]">
                {mode === "mfa_setup"
                  ? "Authenticator code"
                  : "Authenticator or recovery code"}
                <input
                  autoComplete="one-time-code"
                  inputMode="text"
                  required
                  minLength={6}
                  maxLength={64}
                  value={code}
                  onChange={(event) => setCode(event.target.value)}
                  className="mt-2 h-[58px] w-full rounded-xl border border-[#DCE7F3] px-4 text-base text-[#071A3D] outline-none focus:border-[#146EF5] focus:ring-2 focus:ring-[#146EF5]/15"
                />
              </label>
            )}

            {mode === "credentials" && (
              <div className="mt-6 flex items-center justify-between gap-3 text-sm">
                <label className="inline-flex items-center gap-2 text-[#52627A]">
                  <input
                    type="checkbox"
                    checked={rememberMe}
                    onChange={(event) => setRememberMe(event.target.checked)}
                    className="h-5 w-5 rounded border-[#DCE7F3] accent-[#146EF5]"
                  />
                  Remember me
                </label>
                <button
                  type="button"
                  onClick={() => {
                    setMode("forgot")
                    setError(null)
                  }}
                  className="min-h-11 text-[13px] font-medium text-[#146EF5] hover:underline"
                >
                  Forgot password?
                </button>
              </div>
            )}

            {mode !== "account_status" && (
              <button
                type="submit"
                disabled={busy}
                className="mt-7 flex h-[56px] w-full items-center justify-center gap-3 rounded-xl bg-gradient-to-r from-[#0877F9] to-[#146EF5] px-4 text-[15px] font-semibold text-white transition-colors hover:from-[#0F5BD6] hover:to-[#0F5BD6] active:from-[#0B4FC0] active:to-[#0B4FC0] disabled:cursor-not-allowed disabled:opacity-60"
              >
                {busy
                  ? "Signing In..."
                  : mode === "forgot"
                    ? "Send reset instructions"
                    : mode === "mfa_setup"
                      ? "Enable MFA"
                      : mode === "mfa_verify"
                        ? "Verify and Sign In"
                    : "Sign In"}
                {!busy && mode === "credentials" && <ArrowRight size={22} aria-hidden="true" />}
              </button>
            )}
            {mode === "credentials" && registrationEnabled && (
              <p className="mt-4 text-center text-sm text-[#52627A]">
                Need an account?{" "}
                <a
                  href="/register"
                  className="font-medium text-[#146EF5] hover:underline"
                >
                  Request an account
                </a>
              </p>
            )}
            {mode !== "credentials" && (
              <button
                type="button"
                onClick={() => {
                  setMode("credentials")
                  setError(null)
                  setCode("")
                  setAccountStatus(null)
                }}
                className="mt-4 w-full text-sm font-medium text-[#52627A] hover:text-[#071A3D]"
              >
                Back to sign in
              </button>
            )}
          </form>
          <div className="mt-5 flex items-center justify-center gap-3 border-t border-[#DCE7F3] pt-5 text-center text-xs leading-5 text-[#52627A]">
            <ShieldCheck size={20} className="shrink-0 text-[#5476C7]" aria-hidden="true" />
            <p>Access is provided to accounts created by your organization.</p>
          </div>
        </div>
      </section>
    </main>
  )
}
