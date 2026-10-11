import { describe, expect, it } from "vitest"
import { deriveDocumentLifecycleStatus } from "../domain/documentLifecycle"

describe("deriveDocumentLifecycleStatus", () => {
  it("applies processing precedence over every review state", () => {
    for (const processing of [
      "failed",
      "processing",
      "uploaded",
      "queued",
    ] as const) {
      const expected =
        processing === "failed"
          ? "failed"
          : processing === "processing"
            ? "processing"
            : "uploaded"
      for (const review of [
        "not_required",
        "pending",
        "in_review",
        "approved",
        "rejected",
      ] as const) {
        expect(deriveDocumentLifecycleStatus(processing, review)).toBe(expected)
      }
    }
  })

  it("maps completed review states and keeps no-review extracted distinct from approved", () => {
    expect(deriveDocumentLifecycleStatus("completed", "rejected")).toBe(
      "rejected",
    )
    expect(deriveDocumentLifecycleStatus("completed", "approved")).toBe(
      "approved",
    )
    expect(deriveDocumentLifecycleStatus("completed", "in_review")).toBe(
      "in_review",
    )
    expect(deriveDocumentLifecycleStatus("completed", "pending")).toBe(
      "in_review",
    )
    expect(deriveDocumentLifecycleStatus("completed", "not_required")).toBe(
      "extracted",
    )
  })
})
