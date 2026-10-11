/**
 * Cognate AI — Typed REST API Client
 * Connects to the FastAPI backend at http://127.0.0.1:8001/api/v1
 *
 * All functions return the parsed JSON body typed against the backend schemas.
 * On failure they throw an Error with a human-readable message.
 */

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "/api/v1"
const API_TIMEOUT_MS = 10000
let refreshInFlight: Promise<void> | null = null

export class ApiError extends Error {
  constructor(
    readonly status: number,
    detail: string,
    readonly data?: unknown,
  ) {
    super(`API ${status}: ${detail}`)
    this.name = "ApiError"
  }
}

export function safeApiErrorMessage(
  error: unknown,
  restricted = "Access restricted",
) {
  if (error instanceof ApiError) {
    if (error.status === 403) return restricted
    if (error.status >= 500)
      return `Service error (HTTP ${error.status}). Please retry.`
    return `Request failed (HTTP ${error.status}). Please retry.`
  }
  if (error instanceof Error && /timed out/i.test(error.message))
    return "The request timed out. Please retry."
  return "Unable to connect to the service. Please retry."
}

export interface AuthUser {
  id: string
  email: string
  display_name: string | null
  role: string
}

export function getAccessToken(): string | null {
  // Session credentials are HttpOnly cookies and are intentionally unreadable to JavaScript.
  return null
}

export function clearAccessToken(): void {
  window.dispatchEvent(new Event("cognate-auth-expired"))
}

export async function login(
  email: string,
  password: string,
  rememberMe = false,
): Promise<AuthUser> {
  await apiFetch<{ ready: boolean }>("/auth/csrf")
  const result = await apiFetch<{
    user?: AuthUser
    status?: string
    message?: string
    rejection_reason?: string | null
  }>("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, remember_me: rememberMe }),
  })
  if (result.status === "pending_mfa")
    throw new ApiError(202, "MFA verification required")
  if (result.status && result.status !== "approved")
    throw new ApiError(202, result.message ?? result.status, {
      status: result.status,
      rejection_reason: result.rejection_reason,
    })
  if (!result.user) throw new ApiError(401, "Authentication failed")
  return result.user
}

export async function loginWithMfa(
  email: string,
  password: string,
  code: string,
  rememberMe = false,
): Promise<AuthUser> {
  void email
  void password
  void rememberMe
  const result = await apiFetch<{ user: AuthUser }>("/auth/mfa/verify-login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code }),
  })
  return result.user
}

export async function beginMfaSetup(): Promise<string> {
  const result = await apiFetch<{ provisioning_uri: string }>(
    "/auth/mfa/setup",
    { method: "POST" },
  )
  return result.provisioning_uri
}

export async function enableMfa(code: string): Promise<string[]> {
  const result = await apiFetch<{ enabled: boolean; recovery_codes: string[] }>(
    "/auth/mfa/enable",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code }),
    },
  )
  return result.recovery_codes
}

export async function logout(): Promise<void> {
  await apiFetch<void>("/auth/logout", { method: "POST" })
  window.dispatchEvent(new Event("cognate-auth-logout"))
}

export async function fetchCurrentUser(): Promise<AuthUser> {
  return apiFetch("/auth/me")
}

export type GlobalSearchItem = {
  id: string
  display_label: string
  status: "uploaded" | "processing" | "failed" | "extracted" | "in_review" | "approved" | "rejected"
  type: "document" | "patient" | "finding"
}

export type GlobalSearchResponse = {
  documents: GlobalSearchItem[]
  patients: GlobalSearchItem[]
  findings: GlobalSearchItem[]
}

export async function fetchGlobalSearch(query: string): Promise<GlobalSearchResponse> {
  return apiFetch("/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ q: query }),
  })
}

export async function refreshAuthSession(): Promise<AuthUser> {
  const result = await apiFetch<{ user: AuthUser }>(
    "/auth/refresh",
    { method: "POST" },
    false,
  )
  return result.user
}

export async function requestPasswordReset(
  email: string,
): Promise<{ message: string }> {
  await apiFetch<{ ready: boolean }>("/auth/csrf")
  return apiFetch("/auth/forgot-password", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  })
}

export async function resetPassword(token: string, password: string) {
  await apiFetch<{ ready: boolean }>("/auth/csrf")
  return apiFetch<{ message: string }>("/auth/reset-password", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      grant: token,
      new_password: password,
      confirm_password: password,
    }),
  })
}

export async function verifyResetCode(email: string, code: string) {
  await apiFetch<{ ready: boolean }>("/auth/csrf")
  return apiFetch<{ grant: string; expires_in: number }>(
    "/auth/verify-reset-code",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, code }),
    },
  )
}

export async function verifyRegistrationEmail(email: string, code: string) {
  await apiFetch<{ ready: boolean }>("/auth/csrf")
  return apiFetch<{ status: string; message: string }>("/auth/verify-email", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, code }),
  })
}

export async function resendVerificationEmail(email: string) {
  await apiFetch<{ ready: boolean }>("/auth/csrf")
  return apiFetch<{ message: string }>("/auth/resend-verification", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  })
}

export async function acceptInvitation(token: string, password: string) {
  await apiFetch<{ ready: boolean }>("/auth/csrf")
  return apiFetch<{ status: string; message: string }>(
    "/admin/invitations/accept",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token, password }),
    },
  )
}

export async function changePassword(
  currentPassword: string,
  newPassword: string,
) {
  return apiFetch<{ message: string }>("/auth/change-password", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      current_password: currentPassword,
      new_password: newPassword,
    }),
  })
}

export async function fetchAuthConfig() {
  return apiFetch<{
    registration_mode: "approval" | "invite_only" | "disabled"
    self_registration_enabled: boolean
    organizations: { id: string; name: string }[]
  }>("/auth/config")
}
export async function selfRegister(data: {
  work_email: string
  full_name: string
  organization_id?: string
  organization_request_name?: string
  professional_role: "doctor" | "lab_technician" | "other"
  license_or_certification_number?: string
  license_type?: string
  phone?: string
  password: string
  confirm_password: string
  accepted_terms: true
}) {
  await apiFetch<{ ready: boolean }>("/auth/csrf")
  return apiFetch<{ message: string }>("/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  })
}

export interface AccountRequest {
  id: string
  full_name: string
  email: string
  professional_role_requested: string | null
  license_or_certification_number: string | null
  license_type: string | null
  requested_organization_name: string | null
  created_at: string
}
export async function fetchAccountRequests(options: { page?: number; pageSize?: number; q?: string } = {}) {
  const params = new URLSearchParams()
  if (options.page) params.set("page", String(options.page))
  if (options.pageSize) params.set("page_size", String(options.pageSize))
  if (options.q) params.set("q", options.q)
  return apiFetch<{ items: AccountRequest[]; total: number; page: number; page_size: number; has_next: boolean } | AccountRequest[]>(`/admin/account-requests${params.toString() ? `?${params}` : ""}`)
}
export async function approveAccountRequest(id: string, role: string, confirmPrivileged = false, expectedUpdatedAt?: string) {
  return apiFetch<{
    status: string
    email_delivery: "queued" | "not_configured"
    warning?: string
  }>(`/admin/account-requests/${encodeURIComponent(id)}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ role, confirm_privileged: confirmPrivileged, expected_updated_at: expectedUpdatedAt }),
  })
}
export async function rejectAccountRequest(id: string, reason: string) {
  return apiFetch<{
    status: string
    email_delivery: "queued" | "not_configured"
  }>(`/admin/account-requests/${encodeURIComponent(id)}/reject`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reason }),
  })
}

export interface ManagedUser {
  id: string
  email: string
  full_name: string | null
  role: string
  is_active: boolean
  pending_approval: boolean
  mfa_enabled: boolean
  session_count?: number
  updated_at?: string
}
export interface ManagedUsersPage {
  items: ManagedUser[]
  total: number
  page: number
  page_size: number
  has_next: boolean
}
export interface ManagedSession {
  family_id: string
  created_at: string
  expires_at: string
}
export async function fetchManagedUsers(options: { page?: number; pageSize?: number; q?: string; role?: string; status?: string; mfa?: string } = {}) {
  const params = new URLSearchParams()
  if (options.page) params.set("page", String(options.page))
  if (options.pageSize) params.set("page_size", String(options.pageSize))
  if (options.q) params.set("q", options.q)
  if (options.role) params.set("role", options.role)
  if (options.status) params.set("status", options.status)
  if (options.mfa) params.set("mfa", options.mfa)
  return apiFetch<ManagedUsersPage | ManagedUser[]>(`/admin/users${params.toString() ? `?${params}` : ""}`)
}
export async function inviteManagedUser(data: {
  email: string
  full_name: string
  role: string
  confirm_privileged?: boolean
}) {
  return apiFetch<{
    status: string
    email_delivery: "queued" | "not_configured"
    warning?: string
  }>("/admin/invitations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  })
}
export async function updateManagedUserRole(id: string, role: string, confirmPrivileged = false, expectedUpdatedAt?: string) {
  return apiFetch<{ status: string; role: string; warning?: string }>(
    `/admin/users/${encodeURIComponent(id)}/role`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role, confirm_privileged: confirmPrivileged, expected_updated_at: expectedUpdatedAt }),
    },
  )
}
export async function setManagedUserActive(id: string, active: boolean, expectedUpdatedAt?: string) {
  const suffix = expectedUpdatedAt ? `?expected_updated_at=${encodeURIComponent(expectedUpdatedAt)}` : ""
  return apiFetch<{ status: string }>(
    `/admin/users/${encodeURIComponent(id)}/${
      active ? "reactivate" : "deactivate"
    }${suffix}`,
    { method: "POST" },
  )
}
export async function fetchManagedSessions(id: string) {
  return apiFetch<ManagedSession[]>(
    `/admin/users/${encodeURIComponent(id)}/sessions`,
  )
}
export async function revokeManagedSession(id: string, familyId: string) {
  return apiFetch<{ status: string }>(
    `/admin/users/${encodeURIComponent(id)}/sessions/${encodeURIComponent(familyId)}`,
    { method: "DELETE" },
  )
}

// ---------------------------------------------------------------------------

// Shared types

// ---------------------------------------------------------------------------

export interface PaginatedResponse<T> {
  items: T[]

  total: number

  page: number

  page_size: number

  has_next: boolean
}

// ---------------------------------------------------------------------------

// Dashboard

// ---------------------------------------------------------------------------

export interface DashboardMetrics {
  total_documents: number

  processed: number

  pending_review: number

  failed: number

  success_rate: number | null

  last_updated_at: string
}

export interface ReviewQueueSummary {
  high_priority: number

  medium_priority: number

  standard: number

  ai_conflicts: number | null
}

export interface ExtractionQualityItem {
  entity_type: string
  model_confidence_uncalibrated: number | null
}

export interface RecentCaseItem {
  id: string

  patient_name: string | null

  mrn: string | null

  doc_type: string

  status: string

  confidence: string

  review_status: string

  last_updated: string

  entity_counts: Record<string, number>
}

export interface DashboardResponse {
  metrics: DashboardMetrics

  review_queue_summary: ReviewQueueSummary

  extraction_quality: ExtractionQualityItem[]

  recent_cases: RecentCaseItem[]
}

export async function fetchDashboard(): Promise<DashboardResponse> {
  return apiFetch("/dashboard")
}

// ---------------------------------------------------------------------------

// Review

// ---------------------------------------------------------------------------

export interface DocumentReviewSummary {
  id: string

  file_name: string

  document_type: string

  created_at?: string | null
}

export interface PatientReviewSummary {
  id: string

  display_name: string

  mrn: string
}

export interface EntityReviewSummary {
  id: string

  type: string

  raw_text: string

  normalized_value?: string | null

  confidence: number
  assertion: "present" | "absent" | "possible" | "historical" | "family" | "hypothetical"
  section: string | null
  status: string

  details?: Record<string, any> | null
  original_ai_value?: string | null
}

export interface EvidenceReviewSummary {
  id?: string | null

  text: string

  start_offset: number

  end_offset: number

  page_number: number
}

export interface ValidationReviewSummary {
  rule_code?: string | null
  severity?: string | null
  status: string
  message?: string | null
}

export interface ReviewTask {
  id: string

  document_id: string

  entity_id: string | null

  priority: string

  reason: string

  status: string

  assigned_to: string | null

  created_at: string

  started_at: string | null

  completed_at: string | null

  decision: string | null

  comment: string | null

  document?: DocumentReviewSummary | null

  patient?: PatientReviewSummary | null

  entity?: EntityReviewSummary | null

  evidence?: EvidenceReviewSummary | null

  validation?: ValidationReviewSummary | null
  validation_results?: ValidationReviewSummary[]
  source_text?: string | null
}

export interface ReviewStats {
  pending: number

  high_priority: number

  approved: number

  rejected: number
}

export interface NotificationItem {
  id: string
  priority: string
  created_at: string
  document_type: string
}

export interface NotificationsResponse {
  pending_count: number
  items: NotificationItem[]
}

export interface ReviewDecisionPayload {
  decision: string // 'approved' | 'rejected' | 'corrected'

  comment?: string

  corrected_value?: string
}

export async function fetchReviewQueue(
  page = 1,

  pageSize = 50,

  priority?: string,

  status = "pending",

  search?: string,

  documentId?: string,
): Promise<PaginatedResponse<ReviewTask>> {
  const params = new URLSearchParams({
    page: String(page),

    page_size: String(pageSize),
  })

  if (status) params.set("status", status)

  if (priority && priority !== "all") params.set("priority", priority)

  if (search) params.set("search", search)

  if (documentId) params.set("document_id", documentId)

  return apiFetch(`/review/queue?${params}`)
}

export async function fetchReviewTaskDetail(
  taskId: string,
): Promise<ReviewTask> {
  return apiFetch(`/review/${taskId}`)
}

export async function startReviewTask(taskId: string): Promise<ReviewTask> {
  return apiFetch(`/review/${taskId}/start`, { method: "POST" })
}

export async function fetchReviewStats(): Promise<ReviewStats> {
  return apiFetch("/review/stats")
}

export async function fetchNotifications(): Promise<NotificationsResponse> {
  return apiFetch("/notifications")
}

export async function submitReviewDecision(
  taskId: string,

  payload: ReviewDecisionPayload,
): Promise<ReviewTask> {
  return apiFetch(`/review/${taskId}/decision`, {
    method: "POST",

    headers: { "Content-Type": "application/json" },

    body: JSON.stringify(payload),
  })
}

export async function approveReviewTask(
  taskId: string,
  comment?: string,
): Promise<ReviewTask> {
  const params = comment ? `?comment=${encodeURIComponent(comment)}` : ""

  return apiFetch(`/review/${taskId}/approve${params}`, { method: "POST" })
}

export async function rejectReviewTask(
  taskId: string,
  reason?: string,
): Promise<ReviewTask> {
  const params = reason ? `?reason=${encodeURIComponent(reason)}` : ""

  return apiFetch(`/review/${taskId}/reject${params}`, { method: "POST" })
}

export async function correctReviewTask(
  taskId: string,

  correctedValue: string,

  comment?: string,
): Promise<ReviewTask> {
  const params = new URLSearchParams({ corrected_value: correctedValue })

  if (comment) params.set("comment", comment)

  return apiFetch(`/review/${taskId}/correct?${params}`, { method: "POST" })
}

export async function approveCleanReviewItems(
  documentId: string,
): Promise<{ approved_count: number }> {
  return apiFetch(`/review/documents/${documentId}/approve-clean`, {
    method: "POST",
  })
}

export interface ReviewPolicy {
  policy: "all" | "threshold"
  confidence_threshold: number
  high_priority_threshold: number
}

export async function fetchReviewPolicy(): Promise<ReviewPolicy> {
  return apiFetch("/review/policy")
}

// ---------------------------------------------------------------------------

// AI Operations

// ---------------------------------------------------------------------------

export interface AIOpsMetrics {
  total_jobs: number

  running_jobs: number

  completed_jobs: number

  failed_jobs: number

  avg_processing_ms: number | null

  avg_processing_sec: number | null

  avg_confidence: number | null

  ocr_success_rate: number | null

  extraction_accuracy: number | null
  latest_eval: {
    fixtures_evaluated: number
    f1_by_type: Record<string, number>
    precision_by_type: Record<string, number>
    recall_by_type: Record<string, number>
    assertion_accuracy: number
  } | null
}

export interface AIOpsJob {
  job_id: string

  document_id: string

  case_id: string

  doc_type: string

  pipeline_version: string

  status: string

  created_at: string

  processing_ms: number | null
  warning_count: number
  step_count: number
}

export interface AIOpsHealth {
  status: string

  active_jobs: number

  avg_confidence: number | null

  pipeline: string
}

export async function fetchAIOpsMetrics(): Promise<AIOpsMetrics> {
  return apiFetch("/aiops/metrics")
}

export async function fetchAIOpsJobs(
  limit = 20,
): Promise<{ jobs: AIOpsJob[] }> {
  return apiFetch(`/aiops/jobs?limit=${limit}`)
}

export async function fetchAIOpsHealth(): Promise<AIOpsHealth> {
  return apiFetch("/aiops/health")
}

export interface FHIRMetadataCheck {
  configured: boolean
  reachable: boolean
  status?: 'connected' | 'not_configured' | 'unavailable'
  reason?: string
  server_name?: string
  fhir_version?: string
  resource: { fhirVersion?: string; [key: string]: unknown } | null
}

export async function fetchFHIRMetadata(): Promise<FHIRMetadataCheck> {
  return apiFetch("/integrations/fhir/metadata")
}

export async function fetchDocumentFHIR(documentId: string): Promise<Record<string, unknown>> {
  return apiFetch("/documents/" + encodeURIComponent(documentId) + "/fhir")
}

export async function pushSyntheticFHIR(documentId: string): Promise<{
  document_id: string
  status: string
  attempts?: number
  http_status?: number
}> {
  return apiFetch("/integrations/fhir/push/" + encodeURIComponent(documentId), { method: "POST" })
}

export interface AuditEvent {
  id: string

  action: string

  resource_type: string | null

  resource_id: string | null

  user: string

  metadata: Record<string, unknown> | null

  created_at: string
}

export async function fetchAuditEvents(
  limit = 50,
  resourceId?: string,
): Promise<{ items: AuditEvent[] }> {
  const params = new URLSearchParams({ limit: String(limit) })
  if (resourceId) params.set("resource_id", resourceId)
  return apiFetch("/audit/events?" + params.toString())
}

// ---------------------------------------------------------------------------

// Patients

// ---------------------------------------------------------------------------

export interface Patient {
  id: string

  external_patient_id: string | null

  mrn: string | null

  first_name: string | null

  last_name: string | null

  gender: string | null

  dob: string | null
}

export interface TimelineEvent {
  id: string

  type: "encounter" | "document" | string

  title: string

  date: string

  status: string

  detail: string

  external_encounter_id?: string | null

  los_hours?: number | null

  entities?: string[]
}

export interface PatientTimeline {
  patient_id: string

  external_patient_id: string | null

  mrn: string | null

  full_name: string | null

  gender: string | null

  dob: string | null

  timeline_events: TimelineEvent[]
}

export async function fetchPatients(
  page = 1,

  pageSize = 25,

  search?: string,
): Promise<PaginatedResponse<Patient>> {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  })

  if (search) params.set("search", search)

  return apiFetch(`/patients?${params}`)
}

export async function fetchPatientTimeline(
  patientId: string,
): Promise<PatientTimeline> {
  return apiFetch(`/patients/${patientId}/timeline`)
}

// ---------------------------------------------------------------------------

// Documents

// ---------------------------------------------------------------------------

export interface DocumentItem {
  id: string

  case_id: string
  file_name?: string | null

  patient_name: string | null

  mrn: string | null

  doc_type: string

  status: string
  lifecycle_status?: "uploaded" | "processing" | "failed" | "extracted" | "in_review" | "approved" | "rejected"
  review_status?: "not_required" | "pending" | "in_review" | "approved" | "rejected"
  confidence: string

  last_updated: string
}

export interface PipelineStageItem {
  name: string

  status: string

  detail: string

  throughput: string
}

export interface DocumentDetailResponse extends DocumentItem {
  dob: string | null

  source_text: string

  version_number: number

  page_count: number

  file_name: string

  mime_type: string

  size_bytes: number

  pipeline_stages: PipelineStageItem[]
}

export interface DocumentProcessResponse {
  job_id: string

  document_id: string

  status: string

  message: string
}

export interface EvidenceSpanItem {
  id: string

  entity_id: string

  start_offset: number

  end_offset: number

  exact_text: string

  sentence_text?: string | null

  section_name?: string | null
}

export interface ClinicalEntityItem {
  id: string

  extraction_id: string

  entity_type: string

  raw_text: string

  normalized_value: string

  confidence: number
  assertion: "present" | "absent" | "possible" | "historical" | "family" | "hypothetical"
  section: string | null
  status: string

  details?: Record<string, any> | null
  original_ai_value?: string | null
  validation_rule_codes?: string[]
  evidence_spans: EvidenceSpanItem[]
}

export async function fetchDocuments(
  page = 1,

  pageSize = 25,

  status?: string,

  search?: string,
  unlinkedPatient = false,
  sort = "updated_desc",
): Promise<PaginatedResponse<DocumentItem>> {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  })

  if (status) params.set("status", status)

  if (search) params.set("search", search)
  if (unlinkedPatient) params.set("unlinked_patient", "true")
  params.set("sort", sort)

  return apiFetch(`/documents?${params}`)
}

export async function uploadDocument(
  formData: FormData,
): Promise<DocumentItem> {
  return apiFetch("/documents/upload", {
    method: "POST",

    body: formData,
  })
}

export async function processDocument(
  documentId: string,
): Promise<DocumentProcessResponse> {
  return apiFetch(`/documents/${documentId}/process`, {
    method: "POST",
  })
}

export async function retryDocumentProcessing(
  documentId: string,
): Promise<DocumentProcessResponse> {
  return apiFetch(`/documents/${documentId}/process/retry`, {
    method: "POST",
  })
}

export async function reprocessDocument(
  documentId: string,
): Promise<DocumentProcessResponse> {
  return apiFetch(`/documents/${documentId}/reprocess`, {
    method: "POST",
  })
}

export async function fetchDocumentDetails(
  documentId: string,
): Promise<DocumentDetailResponse> {
  return apiFetch(`/documents/${documentId}`)
}

export async function fetchDocumentEntities(
  documentId: string,
): Promise<ClinicalEntityItem[]> {
  return apiFetch(`/documents/${documentId}/entities`)
}

export async function fetchDocumentEvidence(
  documentId: string,
): Promise<EvidenceSpanItem[]> {
  return apiFetch(`/documents/${documentId}/evidence`)
}

export async function fetchProcessingJob(jobId: string): Promise<AIOpsJob> {
  return apiFetch(`/processing/${jobId}`)
}

// ---------------------------------------------------------------------------

// Health / System Status

// ---------------------------------------------------------------------------

export type SystemStatusCode = "healthy" | "degraded" | "unavailable" | "unknown"

export interface HealthResponse {
  status: "ok" | "degraded" | string

  service: string

  database: string
}

/** Calls GET /api/v1/health — returns HTTP 200 when healthy, 503 when degraded. */

export async function fetchHealthStatus(): Promise<HealthResponse> {
  return apiFetch("/health", { signal: AbortSignal.timeout(5000) }, true, true)
}

// ---------------------------------------------------------------------------

// Core fetch helper

// ---------------------------------------------------------------------------

export async function apiFetch<T>(
  path: string,
  init?: RequestInit,
  allowRefresh = true,
  allowErrorStatus = false,
): Promise<T> {
  const url = `${BASE_URL}${path}`

  const controller = new AbortController()

  const timeout = setTimeout(() => controller.abort(), API_TIMEOUT_MS)

  let res: Response
  const headers = new Headers(init?.headers)
  const method = (init?.method ?? "GET").toUpperCase()
  const csrfCookie = document.cookie
    .split("; ")
    .find((part) => part.startsWith("mdis_csrf="))
    ?.slice("mdis_csrf=".length)
  if (
    !["GET", "HEAD", "OPTIONS"].includes(method) &&
    csrfCookie &&
    !headers.has("X-CSRF-Token")
  ) {
    headers.set("X-CSRF-Token", decodeURIComponent(csrfCookie))
  }
  try {
    res = await fetch(url, {
      ...init,
      cache: "no-store",
      headers,
      credentials: "include",
      signal: init?.signal ?? controller.signal,
    })
  } catch (err) {
    if (
      (err instanceof DOMException &&
        (err.name === "AbortError" || err.name === "TimeoutError")) ||
      controller.signal.aborted
    ) {
      throw new Error("Request timed out")
    }
    throw new Error("Network request failed")
  } finally {
    clearTimeout(timeout)
  }

  if (!res.ok && !allowErrorStatus) {
    let detail = res.statusText

    try {
      const body = await res.json()

      detail = body?.detail ?? detail
    } catch (_) {
      // ignore parse error
    }
    if (
      res.status === 401 &&
      !["/auth/login", "/auth/refresh", "/auth/csrf"].includes(path)
    ) {
      if (allowRefresh) {
        try {
          if (!refreshInFlight) {
            refreshInFlight = apiFetch(
              "/auth/refresh",
              { method: "POST" },
              false,
            )
              .then(() => undefined)
              .finally(() => {
                refreshInFlight = null
              })
          }
          await refreshInFlight
          return apiFetch<T>(path, init, false)
        } catch {
          window.dispatchEvent(new Event("cognate-auth-expired"))
        }
      } else {
        window.dispatchEvent(new Event("cognate-auth-expired"))
      }
    }
    if (
      res.status === 403 &&
      path !== "/auth/login" &&
      path !== "/auth/refresh"
    ) {
      window.dispatchEvent(new CustomEvent("cognate-access-restricted"))
    }
    throw new ApiError(res.status, detail)
  }

  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}
