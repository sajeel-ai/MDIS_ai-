import { describe, expect, it } from "vitest"
import { isDevelopmentAuthBypassEnabled } from "../utils/authBypass"

describe("authentication bypass", () => {
  it("remains disabled in development and production builds", () => {
    expect(isDevelopmentAuthBypassEnabled(true, "true")).toBe(false)
    expect(isDevelopmentAuthBypassEnabled(true, undefined)).toBe(false)
    expect(isDevelopmentAuthBypassEnabled(true, "false")).toBe(false)
    expect(isDevelopmentAuthBypassEnabled(false, "true")).toBe(false)
  })
})
