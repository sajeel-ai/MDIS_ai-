import { useEffect, useState, type FormEvent } from "react"
import {
  CheckCircle2,
  Eye,
  EyeOff,
  FileText,
  LockKeyhole,
  Mail,
  SearchCheck,
  ShieldCheck,
  LoaderCircle,
} from "lucide-react"
import mdisMarkUrl from "../public/Glossy Blue Ribbon M Emblem.png"
import {
  ApiError,
  fetchAuthConfig,
  requestPasswordReset,
} from "../services/api"
import { authErrorMessage, useAuth } from "../auth/AuthProvider"

type LoginMode = "credentials" | "mfa_verify" | "mfa_setup" | "forgot" | "restricted" | "account_status"

const WORKFLOW_STEPS = [
  {
    label: "AI Extraction",
    description: "Extracts key clinical information.",
    Icon: FileText,
  },
  {
    label: "Clinic Review",
    description: "Clinic reviewers validate and approve.",
    Icon: SearchCheck,
  },
  {
    label: "Approved Data",
    description: "Structured, normalized data ready for use.",
    Icon: CheckCircle2,
  },
] as const

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
  const [workflowStep, setWorkflowStep] = useState(0)
  const [sliderPaused, setSliderPaused] = useState(false)
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

  useEffect(() => {
    if (sliderPaused) return
    const timer = window.setInterval(() => {
      setWorkflowStep((current) => (current + 1) % WORKFLOW_STEPS.length)
    }, 5500)
    return () => window.clearInterval(timer)
  }, [sliderPaused])

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
    <main className="login-shell">
      <section className="story-panel">
        <div className="absolute inset-0 overflow-hidden" aria-hidden="true">
          <div className="absolute -right-28 -top-28 h-[30rem] w-[30rem] rounded-full border border-[#1688FF]/35" />
          <div className="absolute -right-12 -top-12 h-[24rem] w-[24rem] rounded-full border border-[#1688FF]/35" />
          <div className="absolute -bottom-48 -left-28 h-[27rem] w-[65rem] rotate-[-12deg] rounded-[50%] border border-[#16C7E8]/25 bg-gradient-to-r from-transparent via-[#146EF5]/15 to-[#146EF5]/50" />
          <div className="absolute bottom-16 left-0 h-px w-[70%] bg-gradient-to-r from-[#16C7E8]/50 to-transparent" />
        </div>
        <div className="story-content">
          <div className="story-header mb-6 flex items-center gap-3">
            <img src={mdisMarkUrl} alt="" className="h-10 w-10 object-contain" />
          </div>
          <div className="mb-5 flex items-center gap-4 text-[11px] font-medium uppercase tracking-[0.16em] text-[#C4D4F4]">
            <span className="h-0.5 w-9 bg-[#16C7E8]" />
            Medical Document Intelligence System
          </div>
          <h1 className="max-w-xl text-3xl font-semibold leading-[1.18] tracking-[-0.02em] xl:text-[38px]">
            Turn medical documents into <span className="text-[#16C7E8]">clinical intelligence.</span>
          </h1>
          <p className="story-description">Structured, validated, and traceable data from every clinical document.</p>
          <div className="mx-auto mt-20 w-full max-w-2xl" onMouseEnter={() => setSliderPaused(true)} onMouseLeave={() => setSliderPaused(false)} onFocus={() => setSliderPaused(true)} onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setSliderPaused(false) }}>
            <div className="min-h-24 p-2 transition-all duration-500 sm:p-3">
              {(() => {
                const step = WORKFLOW_STEPS[workflowStep]
                return (
                  <div key={step.label} className="login-workflow-slide flex min-h-16 items-stretch gap-4 text-left">
                    <span
                      className="mt-0.5 w-1 shrink-0 rounded-full bg-gradient-to-b from-[#16C7E8] via-[#146EF5] to-transparent"
                      aria-hidden="true"
                    />
                    <div>
                      <p className="text-sm font-semibold text-white">{step.label}</p>
                      <p className="mt-1 text-xs leading-5 text-[#C4D4F4]">{step.description}</p>
                    </div>
                  </div>
                )
              })()}
            </div>
            <div className="mt-4 flex items-center justify-center gap-2" role="tablist" aria-label="MDIS workflow">
              {WORKFLOW_STEPS.map((step, index) => (
                <button
                  key={step.label}
                  type="button"
                  role="tab"
                  aria-selected={workflowStep === index}
                  aria-label={`Show ${step.label}`}
                  onClick={() => setWorkflowStep(index)}
                  className={`h-2.5 rounded-full transition-all duration-300 ${workflowStep === index ? "w-8 bg-[#16C7E8]" : "w-2.5 bg-[#7EA9DC]/60 hover:bg-[#C4D4F4]"}`}
                />
              ))}
            </div>
          </div>
        </div>
        <p className="story-footer relative z-10 flex items-center gap-4 text-sm text-[#C4D4F4]">
          <span className="h-0.5 w-9 shrink-0 bg-[#16C7E8]" aria-hidden="true" />
          AI-assisted extraction. Human-approved results.
        </p>
      </section>

      <section className="form-panel">
        <header className="form-panel-header"><span>Organization portal</span><a href="mailto:support@mdis.local">Contact support</a></header>
        <div className="mobile-logo"><img src={mdisMarkUrl} alt="MDIS" className="h-12 w-12 object-contain" /></div>
        <div className="relative my-auto w-full max-w-[520px]">
          <form
            onSubmit={submit}
            className="login-card px-6 py-7 sm:px-10 sm:py-9 lg:px-12 lg:py-10"
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
                  <span className="group relative mt-2 block">
                    <Mail size={18} aria-hidden="true" className="absolute left-4 top-1/2 -translate-y-1/2 text-[#7184B4] transition-colors duration-200 group-focus-within:text-[#146EF5]" />
                    <input
                      autoComplete="username"
                      type="email"
                      required
                      maxLength={256}
                      value={email}
                      onChange={(event) => setEmail(event.target.value)}
                      placeholder=" "
                      aria-label="Email"
                      className="peer h-[54px] w-full rounded-xl border border-[#DCE7F3] bg-white pl-14 pr-4 pt-4 text-[15px] font-normal text-[#071A3D] outline-none placeholder:text-transparent focus:border-[#146EF5] focus:ring-2 focus:ring-[#146EF5]/15"
                    />
                    <span className="pointer-events-none absolute left-14 top-1/2 -translate-y-1/2 text-[15px] font-normal text-[#8292BC] transition-all duration-200 peer-focus:top-2 peer-focus:translate-y-0 peer-focus:text-[10px] peer-focus:font-semibold peer-focus:text-[#146EF5] peer-[:not(:placeholder-shown)]:top-2 peer-[:not(:placeholder-shown)]:translate-y-0 peer-[:not(:placeholder-shown)]:text-[10px] peer-[:not(:placeholder-shown)]:font-semibold peer-[:not(:placeholder-shown)]:text-[#146EF5]">Email</span>
                  </span>
                </label>
              )}

            {mode === "credentials" && (
              <label className="mt-6 block text-sm font-semibold text-[#071A3D]">
                Password
                <span className="group relative mt-2 block">
                  <LockKeyhole size={18} aria-hidden="true" className="absolute left-4 top-1/2 -translate-y-1/2 text-[#7184B4] transition-colors duration-200 group-focus-within:text-[#146EF5]" />
                  <input
                    autoComplete="current-password"
                    type={showPassword ? "text" : "password"}
                    required
                    maxLength={1024}
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    placeholder=" "
                    aria-label="Password"
                    className="peer h-[54px] w-full rounded-xl border border-[#DCE7F3] bg-white pl-14 pr-14 pt-4 text-[15px] font-normal text-[#071A3D] outline-none placeholder:text-transparent focus:border-[#146EF5] focus:ring-2 focus:ring-[#146EF5]/15"
                  />
                  <span className="pointer-events-none absolute left-14 top-1/2 -translate-y-1/2 text-[15px] font-normal text-[#8292BC] transition-all duration-200 peer-focus:top-2 peer-focus:translate-y-0 peer-focus:text-[10px] peer-focus:font-semibold peer-focus:text-[#146EF5] peer-[:not(:placeholder-shown)]:top-2 peer-[:not(:placeholder-shown)]:translate-y-0 peer-[:not(:placeholder-shown)]:text-[10px] peer-[:not(:placeholder-shown)]:font-semibold peer-[:not(:placeholder-shown)]:text-[#146EF5]">Password</span>
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
                className="login-submit group mt-7 flex h-[56px] w-full items-center justify-center gap-3 rounded-xl bg-gradient-to-r from-[#0877F9] to-[#16C7E8] px-4 text-[15px] font-semibold text-white shadow-[0_10px_24px_rgba(20,110,245,0.22)] will-change-transform transition-[transform,box-shadow,filter] duration-[240ms] ease-[cubic-bezier(0.22,1,0.36,1)] hover:-translate-y-px hover:from-[#146EF5] hover:to-[#22D3EE] hover:shadow-[0_14px_30px_rgba(20,110,245,0.35)] active:translate-y-0 active:scale-[0.995] focus-visible:outline-2 focus-visible:outline-offset-3 focus-visible:outline-[#146EF5] disabled:cursor-not-allowed disabled:opacity-60"
              >
                {busy
                  ? <><LoaderCircle size={18} className="animate-spin" aria-hidden="true" /> Signing in…</>
                  : mode === "forgot"
                    ? "Send reset instructions"
                    : mode === "mfa_setup"
                      ? "Enable MFA"
                      : mode === "mfa_verify"
                        ? "Verify and Sign In"
                    : "Sign In"}
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
