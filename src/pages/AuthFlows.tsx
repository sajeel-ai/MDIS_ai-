import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react"
import { KeyRound } from "lucide-react"
import { QRCodeSVG } from "qrcode.react"
import mdisMarkUrl from "../public/Glossy Blue Ribbon M Emblem.png"
import mdisLogoUrl from "../public/Glossy 3D MDIS Ribbon Logo.png"
import {
  ApiError,
  acceptInvitation,
  changePassword,
  enableMfa,
  fetchAuthConfig,
  resetPassword,
  requestPasswordReset,
  selfRegister,
  verifyResetCode,
  verifyRegistrationEmail,
  resendVerificationEmail,
} from "../services/api"
import { useAuth } from "../auth/AuthProvider"

function AuthCard({
  title,
  description,
  children,
  brand = "cognate",
}: {
  title: string
  description: string
  children?: ReactNode
  brand?: "cognate" | "mdis"
}) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-[#F5FAFF] px-4 py-8 sm:px-6">
      <section className="w-full max-w-lg rounded-2xl border border-[#DCE7F3] bg-white p-5 shadow-sm sm:p-8">
        <a
          href="/login"
          aria-label="MDIS sign in"
          title="Back to sign in"
          className="mb-6 inline-flex min-h-11 items-center gap-2 text-sm font-semibold text-[#146EF5]"
        >
          {brand === "mdis" ? (
            <img src={mdisLogoUrl} alt="MDIS" className="h-9 w-auto object-contain" />
          ) : (
            <img src={mdisMarkUrl} alt="MDIS" className="h-9 w-9 object-contain" />
          )}
        </a>
        <h1 className="text-2xl font-semibold text-[#071A3D]">{title}</h1>
        <p className="mt-2 text-sm leading-6 text-[#52627A]">{description}</p>
        {children}
      </section>
    </main>
  )
}

function VerificationCodeFields({
  value,
  setValue,
}: {
  value: string
  setValue: (value: string) => void
}) {
  const inputs = useRef<Array<HTMLInputElement | null>>([])
  const updateDigit = (index: number, digit: string) => {
    const next = value.padEnd(6, " ").split("")
    next[index] = digit
    setValue(next.join("").replace(/\s+$/, ""))
  }

  return (
    <div role="group" aria-label="Six-digit verification code" className="mt-3 grid grid-cols-6 gap-2 sm:gap-3">
      {Array.from({ length: 6 }, (_, index) => (
        <input
          key={index}
          ref={(element) => { inputs.current[index] = element }}
          type="text"
          inputMode="numeric"
          pattern="[0-9]*"
          autoComplete={index === 0 ? "one-time-code" : "off"}
          aria-label={index === 0 ? "Verification code" : `Verification code digit ${index + 1}`}
          required
          maxLength={6}
          value={value[index] ?? ""}
          onChange={(event) => {
            const digits = event.target.value.replace(/\D/g, "")
            if (digits.length > 1) {
              const pasted = digits.slice(0, 6)
              setValue(pasted)
              inputs.current[Math.min(pasted.length, 5)]?.focus()
              return
            }
            updateDigit(index, digits)
            if (digits && index < 5) inputs.current[index + 1]?.focus()
          }}
          onPaste={(event) => {
            event.preventDefault()
            const pasted = event.clipboardData.getData("text").replace(/\D/g, "").slice(0, 6)
            setValue(pasted)
            inputs.current[Math.min(pasted.length, 5)]?.focus()
          }}
          onKeyDown={(event) => {
            if (event.key === "Backspace") {
              event.preventDefault()
              if (value[index]) updateDigit(index, "")
              else if (index > 0) inputs.current[index - 1]?.focus()
            } else if (event.key === "ArrowLeft" && index > 0) {
              inputs.current[index - 1]?.focus()
            } else if (event.key === "ArrowRight" && index < 5) {
              inputs.current[index + 1]?.focus()
            }
          }}
          className="h-12 min-w-0 rounded-xl border border-[#DCE7F3] bg-white text-center text-lg font-semibold text-[#071A3D] outline-none focus:border-[#146EF5] focus:ring-2 focus:ring-[#146EF5]/20"
        />
      ))}
    </div>
  )
}

function PasswordFields({
  password,
  setPassword,
  confirm,
  setConfirm,
}: {
  password: string
  setPassword: (value: string) => void
  confirm: string
  setConfirm: (value: string) => void
}) {
  const strength =
    password.length < 12
      ? "Needs at least 12 characters"
      : password.length < 16
        ? "Passphrase length: good"
        : "Passphrase length: strong"
  return (
    <>
      <label className="mt-5 block text-sm font-medium text-[#071A3D]">
        New password
        <input
          type="password"
          autoComplete="new-password"
          required
          minLength={12}
          maxLength={1024}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="mt-2 h-11 w-full rounded-lg border border-[#DCE7F3] px-3 focus-visible:outline-2 focus-visible:outline-[#146EF5]"
        />
      </label>
      <p aria-live="polite" className="mt-1 text-xs text-[#52627A]">
        {strength}
      </p>
      <p className="mt-2 text-xs leading-5 text-[#52627A]">
        Use at least 12 characters. Common or compromised passwords and
        passwords containing your email or name are rejected. No
        character-composition rules are required.
      </p>
      <label className="mt-4 block text-sm font-medium text-[#071A3D]">
        Confirm new password
        <input
          type="password"
          autoComplete="new-password"
          required
          minLength={12}
          maxLength={1024}
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          className="mt-2 h-11 w-full rounded-lg border border-[#DCE7F3] px-3 focus-visible:outline-2 focus-visible:outline-[#146EF5]"
        />
      </label>
      {confirm && password !== confirm && (
        <p role="alert" className="mt-2 text-sm text-[#B91C1C]">
          Passwords do not match.
        </p>
      )}
    </>
  )
}

function PublicPasswordAction({
  invitation = false,
}: {
  invitation?: boolean
}) {
  const token = new URLSearchParams(window.location.search).get("token") ?? ""
  const [password, setPassword] = useState("")
  const [confirm, setConfirm] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    if (password !== confirm) {
      setError("Passwords do not match.")
      return
    }
    setBusy(true)
    try {
      const result = await acceptInvitation(token, password)
      setMessage(result.message)
    } catch (e) {
      setError(
        e instanceof ApiError && e.status === 422
          ? e.message.replace(/^API 422: /, "")
          : "This link is invalid or expired, or the password could not be accepted.",
      )
    } finally {
      setBusy(false)
    }
  }
  return (
    <AuthCard
      title={invitation ? "Accept invitation" : "Reset password"}
      description={
        invitation
          ? "Set a password to activate your organization account."
          : "Choose a new password for your account."
      }
    >
      {!token ? (
        <p
          role="alert"
          className="mt-5 rounded-lg bg-[#FEF2F2] p-3 text-sm text-[#B91C1C]"
        >
          This link is invalid or expired.
        </p>
      ) : (
        <form onSubmit={submit} noValidate>
          <PasswordFields
            password={password}
            setPassword={setPassword}
            confirm={confirm}
            setConfirm={setConfirm}
          />
          {error && (
            <p
              role="alert"
              aria-live="polite"
              className="mt-4 rounded-lg bg-[#FEF2F2] p-3 text-sm text-[#B91C1C]"
            >
              {error}
            </p>
          )}
          {message && (
            <p
              role="status"
              className="mt-4 rounded-lg bg-[#EAF5FF] p-3 text-sm text-[#071A3D]"
            >
              {message}
            </p>
          )}
          <button
            disabled={busy || password.length < 12 || password !== confirm}
            className="mt-6 min-h-11 w-full rounded-lg bg-[#146EF5] px-4 font-semibold text-white hover:bg-[#0F5BD6] disabled:opacity-50"
          >
            {busy
              ? "Saving…"
              : invitation
                ? "Accept invitation"
                : "Reset password"}
          </button>
        </form>
      )}
    </AuthCard>
  )
}

export function ForgotPasswordPage() {
  const [email, setEmail] = useState("")
  const [message, setMessage] = useState("")
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError("")
    try {
      setMessage((await requestPasswordReset(email)).message)
    } catch (caught) {
      setError(
        caught instanceof ApiError && caught.status === 503
          ? "Email delivery is not configured. Contact your administrator."
          : "Unable to connect to the authentication service.",
      )
    } finally {
      setBusy(false)
    }
  }
  return (
    <AuthCard
      title="Reset your password"
      description="Enter your account email. If the account exists, reset instructions will be sent."
    >
      <form onSubmit={submit}>
        <label className="mt-5 block text-sm font-medium text-[#071A3D]">
          Email
          <input
            type="email"
            autoComplete="email"
            required
            maxLength={256}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="mt-2 h-11 w-full rounded-lg border border-[#DCE7F3] px-3"
          />
        </label>
        {error && (
          <p
            role="alert"
            aria-live="polite"
            className="mt-4 text-sm text-[#B91C1C]"
          >
            {error}
          </p>
        )}
        {message && (
          <p
            role="status"
            className="mt-4 rounded-lg bg-[#EAF5FF] p-3 text-sm text-[#071A3D]"
          >
            {message}
          </p>
        )}
        <button
          disabled={busy}
          className="mt-6 min-h-11 w-full rounded-lg bg-[#146EF5] font-semibold text-white disabled:opacity-50"
        >
          {busy ? "Sending…" : "Send reset instructions"}
        </button>
      </form>
    </AuthCard>
  )
}

export function ResetPasswordPage({
  initialEmail = "",
}: {
  initialEmail?: string
} = {}) {
  const [step, setStep] = useState<"email" | "code" | "password" | "done">(
    () =>
      new URLSearchParams(window.location.search).get("step") === "code"
        ? "code"
        : "email",
  )
  const [email, setEmail] = useState(initialEmail)
  const [code, setCode] = useState("")
  const [grant, setGrant] = useState("")
  const [password, setPassword] = useState("")
  const [confirm, setConfirm] = useState("")
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (busy) return
    setError("")
    setBusy(true)
    try {
      if (step === "email") {
        await requestPasswordReset(email)
        setStep("code")
      } else if (step === "code") {
        const result = await verifyResetCode(email, code.replace(/\s/g, ""))
        setGrant(result.grant)
        setStep("password")
      } else if (password === confirm) {
        await resetPassword(grant, password)
        setStep("done")
      } else setError("Passwords do not match.")
    } catch (caught) {
      setError(
        caught instanceof ApiError && caught.status === 503
          ? "Email delivery is not configured. Contact your administrator."
          : "The request could not be completed. Check the code or try again.",
      )
    } finally {
      setBusy(false)
    }
  }
  return (
    <AuthCard
      title={step === "password" ? "Create new password" : "Reset your password"}
      brand="mdis"
      description={
        step === "email"
          ? "Enter your account email. If the account exists, reset instructions will be sent."
          : step === "code"
            ? "Enter the verification code sent to your email."
            : step === "password"
              ? "Create a new password to secure your account. Make sure it is strong and easy to remember."
              : "Your password has been reset. Sign in with your new password."
      }
    >
      {step !== "done" && (
        <form onSubmit={submit}>
          {(step === "email" || (step === "code" && !email)) && (
            <label className="mt-5 block text-sm font-medium text-[#071A3D]">
              Email
              <input
                type="email"
                autoComplete="email"
                required
                maxLength={256}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="mt-2 h-11 w-full rounded-lg border border-[#DCE7F3] px-3"
              />
            </label>
          )}
          {step === "code" && (
            <>
              <div className="mt-4 text-sm font-medium text-[#071A3D]">
                Verification code
                <VerificationCodeFields value={code} setValue={setCode} />
              </div>
            </>
          )}
          {step === "password" && (
            <>
              <div className="mx-auto mt-5 grid h-12 w-12 place-items-center rounded-xl border border-[#DCE7F3] bg-[#EAF5FF] text-[#146EF5]">
                <KeyRound size={22} aria-hidden="true" />
              </div>
              <PasswordFields
                password={password}
                setPassword={setPassword}
                confirm={confirm}
                setConfirm={setConfirm}
              />
            </>
          )}
          {error && (
            <p
              role="alert"
              aria-live="polite"
              className="mt-4 rounded-lg bg-[#FEF2F2] p-3 text-sm text-[#B91C1C]"
            >
              {error}
            </p>
          )}
          <button
            disabled={
              busy ||
              (step === "code" && code.replace(/\s/g, "").length !== 6) ||
              (step === "password" &&
                (password.length < 12 || password !== confirm))
            }
            className="mt-6 min-h-11 w-full rounded-lg bg-[#146EF5] font-semibold text-white disabled:opacity-50"
          >
            {busy
              ? "Please wait…"
              : step === "email"
                ? "Send reset code"
                : step === "code"
                  ? "Verify code"
                  : "Confirm"}
          </button>
        </form>
      )}
      {step === "done" && (
        <a
          href="/login"
          className="mt-5 inline-flex min-h-11 items-center rounded-lg bg-[#146EF5] px-4 font-semibold text-white"
        >
          Sign in
        </a>
      )}
    </AuthCard>
  )
}
export function AcceptInvitationPage() {
  return <PublicPasswordAction invitation />
}

export function ChangePasswordPage({ onDone }: { onDone: () => void }) {
  const [current, setCurrent] = useState("")
  const [password, setPassword] = useState("")
  const [confirm, setConfirm] = useState("")
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError("")
    if (password !== confirm) {
      setError("Passwords do not match.")
      return
    }
    setBusy(true)
    try {
      await changePassword(current, password)
      window.dispatchEvent(new Event("cognate-auth-logout"))
      onDone()
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 401
          ? "Current password is incorrect."
          : "Unable to change password. Check the password requirements and try again.",
      )
    } finally {
      setBusy(false)
    }
  }
  return (
    <AuthCard
      title="Change password"
      description="Changing your password signs out active sessions. Sign in again with your new password."
    >
      <form onSubmit={submit}>
        <label className="mt-5 block text-sm font-medium text-[#071A3D]">
          Current password
          <input
            type="password"
            autoComplete="current-password"
            required
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            className="mt-2 h-11 w-full rounded-lg border border-[#DCE7F3] px-3"
          />
        </label>
        <PasswordFields
          password={password}
          setPassword={setPassword}
          confirm={confirm}
          setConfirm={setConfirm}
        />
        {error && (
          <p
            role="alert"
            aria-live="polite"
            className="mt-4 text-sm text-[#B91C1C]"
          >
            {error}
          </p>
        )}
        <button
          disabled={busy || password.length < 12 || password !== confirm}
          className="mt-6 min-h-11 w-full rounded-lg bg-[#146EF5] font-semibold text-white disabled:opacity-50"
        >
          {busy ? "Saving…" : "Change password"}
        </button>
      </form>
    </AuthCard>
  )
}

export function MfaSetupPage({
  onComplete,
}: {
  onComplete: (codes: string[]) => void
}) {
  const { beginMfaSetup } = useAuth()
  const [uri, setUri] = useState("")
  const [code, setCode] = useState("")
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  const start = async () => {
    setError("")
    try {
      setUri(await beginMfaSetup())
    } catch {
      setError("MFA setup session expired. Sign in again.")
    }
  }
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError("")
    try {
      onComplete(await enableMfa(code))
    } catch {
      setError("The authenticator code could not be verified.")
    } finally {
      setBusy(false)
    }
  }
  return (
    <AuthCard
      title="Set up multi-factor authentication"
      description="Scan this QR with an authenticator app. Keep the setup value private; it contains your MFA secret."
    >
      <button
        onClick={() => void start()}
        className="mt-5 min-h-11 rounded-lg border border-[#DCE7F3] px-4 text-sm font-semibold text-[#146EF5]"
      >
        Get setup value
      </button>
      {uri && (
        <>
          <div className="mt-4 inline-block rounded-lg border border-[#DCE7F3] bg-white p-3">
            <QRCodeSVG
              value={uri}
              size={180}
              level="M"
              title="Authenticator setup QR code"
            />
          </div>
          <label className="mt-4 block text-sm font-medium text-[#071A3D]">
            Manual setup value
            <input
              readOnly
              value={uri.replace(/^otpauth:\/\/totp\//, "")}
              className="mt-2 h-11 w-full rounded-lg border border-[#DCE7F3] px-3"
            />
          </label>
          <form onSubmit={submit}>
            <label className="mt-4 block text-sm font-medium text-[#071A3D]">
              Authenticator code
              <input
                autoComplete="one-time-code"
                inputMode="numeric"
                required
                minLength={6}
                maxLength={6}
                value={code}
                onChange={(e) => setCode(e.target.value)}
                className="mt-2 h-11 w-full rounded-lg border border-[#DCE7F3] px-3"
              />
            </label>
            {error && (
              <p role="alert" className="mt-3 text-sm text-[#B91C1C]">
                {error}
              </p>
            )}
            <button
              disabled={busy}
              className="mt-5 min-h-11 w-full rounded-lg bg-[#146EF5] font-semibold text-white"
            >
              {busy ? "Verifying…" : "Enable MFA"}
            </button>
          </form>
        </>
      )}
      {!uri && error && (
        <p role="alert" className="mt-4 text-sm text-[#B91C1C]">
          {error}
        </p>
      )}
    </AuthCard>
  )
}

export function MfaVerifyPage({
  onAuthenticated,
}: {
  onAuthenticated: () => void
}) {
  const { login } = useAuth()
  const [code, setCode] = useState("")
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (busy) return
    setBusy(true)
    setError("")
    try {
      await login("", "", false, code)
      onAuthenticated()
    } catch (caught) {
      setError(
        caught instanceof ApiError && caught.status === 401
          ? "Invalid authenticator or recovery code, or the verification session expired."
          : caught instanceof ApiError && caught.status === 403
            ? "Access restricted."
            : "Unable to connect to the authentication service.",
      )
    } finally {
      setBusy(false)
    }
  }
  return (
    <AuthCard
      title="Verify your identity"
      description="Enter an authenticator code or one-time recovery code to finish signing in."
    >
      <form onSubmit={submit}>
        <label className="mt-5 block text-sm font-medium text-[#071A3D]">
          Authenticator or recovery code
          <input
            autoComplete="one-time-code"
            inputMode="text"
            required
            minLength={6}
            maxLength={64}
            value={code}
            onChange={(e) => setCode(e.target.value)}
            className="mt-2 h-11 w-full rounded-lg border border-[#DCE7F3] px-3"
          />
        </label>
        {error && (
          <p
            role="alert"
            aria-live="polite"
            className="mt-3 text-sm text-[#B91C1C]"
          >
            {error}
          </p>
        )}
        <button
          disabled={busy}
          className="mt-4 min-h-11 w-full rounded-lg bg-[#146EF5] font-semibold text-white disabled:opacity-50"
        >
          {busy ? "Verifying…" : "Verify and sign in"}
        </button>
      </form>
    </AuthCard>
  )
}
export function SessionExpiredPage() {
  return (
    <AuthCard
      title="Session expired"
      description="Your session has expired. Please sign in again."
    >
      <a
        href="/login"
        className="mt-5 inline-flex min-h-11 items-center rounded-lg bg-[#146EF5] px-4 font-semibold text-white"
      >
        Sign in
      </a>
    </AuthCard>
  )
}
export function ForbiddenPage() {
  return (
    <AuthCard
      title="Access restricted"
      description="You don't have permission to access this resource."
    >
      <a
        href="/dashboard"
        className="mt-5 inline-flex min-h-11 items-center rounded-lg bg-[#146EF5] px-4 font-semibold text-white"
      >
        Return to dashboard
      </a>
    </AuthCard>
  )
}

export function RegisterPage() {
  const [enabled, setEnabled] = useState(false)
  const [checked, setChecked] = useState(false)
  const [organizations, setOrganizations] = useState<{
    id: string
    name: string
  }[]>([])
  const [email, setEmail] = useState("")
  const [name, setName] = useState("")
  const [organizationId, setOrganizationId] = useState("")
  const [professionalRole, setProfessionalRole] =
    useState<"doctor" | "lab_technician" | "other">("doctor")
  const [password, setPassword] = useState("")
  const [confirm, setConfirm] = useState("")
  const [code, setCode] = useState("")
  const [verification, setVerification] = useState(false)
  const [registrationComplete, setRegistrationComplete] = useState(false)
  const [acceptedTerms, setAcceptedTerms] = useState(false)
  const [message, setMessage] = useState("")
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    let active = true
    void fetchAuthConfig()
      .then((v) => {
        if (active) {
          setEnabled(v.registration_mode === "approval")
          setOrganizations(v.organizations)
          setOrganizationId(v.organizations[0]?.id ?? "")
          setChecked(true)
        }
      })
      .catch(() => {
        if (active) setChecked(true)
      })
    return () => {
      active = false
    }
  }, [])
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (busy) return
    setBusy(true)
    setError("")
    try {
      if (verification) {
        setMessage((await verifyRegistrationEmail(email, code.replace(/\s/g, ""))).message)
        setVerification(false)
        setRegistrationComplete(true)
      } else {
        if (password !== confirm) {
          setError("Passwords do not match.")
          return
        }
        if (!organizationId) {
          setError("No organization is available for registration.")
          return
        }
        setMessage(
          (
            await selfRegister({
              work_email: email,
              full_name: name,
              organization_id: organizationId,
              professional_role: professionalRole,
              password,
              confirm_password: confirm,
              accepted_terms: true,
            })
          ).message,
        )
        setVerification(true)
      }
    } catch (caught) {
      setError(
        caught instanceof ApiError && caught.status === 503
          ? "Email delivery is not configured. Contact your administrator."
          : "Unable to complete registration. Check the details and try again.",
      )
    } finally {
      setBusy(false)
    }
  }
  if (!checked)
    return (
      <AuthCard
        title="Checking registration"
        description="Loading account options…"
      />
    )
  if (!enabled)
    return (
      <AuthCard
        title="Registration unavailable"
        description="This organization is not accepting public registrations."
      >
        <a
          href="/login"
          className="mt-5 inline-flex min-h-11 items-center rounded-lg bg-[#146EF5] px-4 font-semibold text-white"
        >
          Return to sign in
        </a>
      </AuthCard>
    )
  if (registrationComplete)
    return (
      <AuthCard
        title="Email verified"
        description="Your account request is awaiting organization approval."
      >
        <a
          href="/login"
          className="mt-5 inline-flex min-h-11 items-center rounded-lg bg-[#146EF5] px-4 font-semibold text-white"
        >
          Return to sign in
        </a>
      </AuthCard>
    )
  return (
    <AuthCard
      title={verification ? "Verify your email" : "Request an account"}
      brand={verification ? "mdis" : "cognate"}
      description={
        verification
          ? "Enter the code sent to your email. Your account will then await organization approval."
          : "New accounts remain inactive until an administrator approves them."
      }
    >
      <form onSubmit={submit}>
        {!verification && (
          <>
            <label className="mt-4 block text-sm">
              Full name
              <input
                required
                autoComplete="name"
                maxLength={128}
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="mt-1 h-11 w-full rounded-lg border border-[#DCE7F3] px-3"
              />
            </label>
            <label className="mt-4 block text-sm">
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
            <label className="mt-4 block text-sm">
              Organization
              <select
                required
                value={organizationId}
                onChange={(e) => setOrganizationId(e.target.value)}
                className="mt-1 h-11 w-full rounded-lg border border-[#DCE7F3] px-3"
              >
                <option value="">Select organization</option>
                {organizations.map((org) => (
                  <option key={org.id} value={org.id}>
                    {org.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="mt-4 block text-sm">
              Professional role
              <select
                value={professionalRole}
                onChange={(e) =>
                  setProfessionalRole(e.target.value as typeof professionalRole)
                }
                className="mt-1 h-11 w-full rounded-lg border border-[#DCE7F3] px-3"
              >
                <option value="doctor">Doctor</option>
                <option value="lab_technician">Lab technician</option>
                <option value="other">Other</option>
              </select>
            </label>
            <PasswordFields
              password={password}
              setPassword={setPassword}
              confirm={confirm}
              setConfirm={setConfirm}
            />
            <label className="mt-4 flex min-h-11 items-center gap-2 text-sm text-[#52627A]">
              <input
                type="checkbox"
                required
                checked={acceptedTerms}
                onChange={(event) => setAcceptedTerms(event.target.checked)}
              />
              I accept the account registration terms.
            </label>
          </>
        )}
        {verification && (
          <>
            <p className="mt-3 text-sm text-[#52627A]" role="status">
              {message}
            </p>
            <div className="mt-4 text-sm">
              Verification code
              <VerificationCodeFields value={code} setValue={setCode} />
            </div>
            <button
              type="button"
              className="mt-3 min-h-11 text-sm font-medium text-[#146EF5]"
              onClick={async () => {
                try {
                  setMessage((await resendVerificationEmail(email)).message)
                } catch {
                  setError("Unable to resend the verification code.")
                }
              }}
            >
              Resend code
            </button>
          </>
        )}
        {error && (
          <p
            role="alert"
            aria-live="polite"
            className="mt-3 text-sm text-[#B91C1C]"
          >
            {error}
          </p>
        )}
        {!verification && message && (
          <p role="status" className="mt-3 text-sm text-[#071A3D]">
            {message}
          </p>
        )}
        <button
          disabled={
            busy ||
            (verification && code.replace(/\s/g, "").length !== 6) ||
            (!verification &&
              (password.length < 12 || password !== confirm || !acceptedTerms))
          }
          className="mt-5 min-h-11 w-full rounded-lg bg-[#146EF5] font-semibold text-white disabled:opacity-50"
        >
          {busy
            ? "Submitting…"
            : verification
              ? "Verify email"
              : "Request account"}
        </button>
      </form>
    </AuthCard>
  )
}
