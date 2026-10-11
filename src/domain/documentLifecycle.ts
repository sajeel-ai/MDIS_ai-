export type ProcessingStatus = "uploaded" | "queued" | "processing" | "completed" | "failed" | string
export type ReviewStatus = "not_required" | "pending" | "in_review" | "approved" | "rejected" | string
export type LifecycleStatus = "uploaded" | "processing" | "failed" | "extracted" | "in_review" | "approved" | "rejected"

/** User-facing status precedence. Processing state always wins over stale review data. */
export function deriveDocumentLifecycleStatus(
  processingStatus: ProcessingStatus,
  reviewStatus: ReviewStatus = "not_required",
): LifecycleStatus {
  if (processingStatus === "failed") return "failed"
  if (processingStatus === "processing") return "processing"
  if (processingStatus === "uploaded" || processingStatus === "queued") return "uploaded"
  if (reviewStatus === "rejected") return "rejected"
  if (reviewStatus === "approved") return "approved"
  if (reviewStatus === "pending" || reviewStatus === "in_review") return "in_review"
  return "extracted"
}

export const lifecycleStatusLabel: Record<LifecycleStatus, string> = {
  uploaded: "Uploaded",
  processing: "Processing",
  failed: "Failed",
  extracted: "Extracted (no review required)",
  in_review: "In review",
  approved: "Approved",
  rejected: "Rejected",
}
