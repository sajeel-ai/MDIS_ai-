import { afterEach, describe, expect, it, vi } from "vitest"

describe("central API client session handling", () => {
  afterEach(() => {
    vi.restoreAllMocks()
    document.cookie = "mdis_csrf=; Max-Age=0; path=/"
    window.dispatchEvent(new Event("cognate-auth-expired"))
  })

  it("uses one refresh request for concurrent 401 responses before retrying both requests", async () => {
    document.cookie = "mdis_csrf=synthetic-csrf; path=/"
    const protectedAttempts = new Map<string, number>()
    let refreshCalls = 0
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async (input) => {
        const url = String(input)
        if (url.endsWith("/auth/refresh")) {
          refreshCalls += 1
          await new Promise((resolve) => setTimeout(resolve, 5))
          return new Response("{}", { status: 200 })
        }
        const path = url.endsWith("/documents") ? "documents" : "patients"
        const attempt = protectedAttempts.get(path) ?? 0
        protectedAttempts.set(path, attempt + 1)
        if (attempt === 0)
          return new Response(JSON.stringify({ detail: "expired" }), {
            status: 401,
          })
        return new Response(JSON.stringify({ path }), { status: 200 })
      })
    const { apiFetch } = await import("../services/api")

    const [documents, patients] = await Promise.all([
      apiFetch<{ path: string }>("/documents"),
      apiFetch<{ path: string }>("/patients"),
    ])

    expect(documents.path).toBe("documents")
    expect(patients.path).toBe("patients")
    expect(refreshCalls).toBe(1)
    expect(fetchMock).toHaveBeenCalledTimes(5)
  })

  it("announces session expiry when refresh also returns 401", async () => {
    document.cookie = "mdis_csrf=synthetic-csrf; path=/"
    const expired = vi.fn()
    window.addEventListener("cognate-auth-expired", expired)
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "expired" }), { status: 401 }),
    )
    const { apiFetch, ApiError } = await import("../services/api")

    await expect(apiFetch("/documents")).rejects.toBeInstanceOf(ApiError)
    expect(expired).toHaveBeenCalledOnce()
    window.removeEventListener("cognate-auth-expired", expired)
  })

  it("signals forbidden access without treating a 403 as an expired session", async () => {
    const restricted = vi.fn()
    window.addEventListener("cognate-access-restricted", restricted)
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "forbidden" }), { status: 403 }),
    )
    const { apiFetch, ApiError } = await import("../services/api")

    await expect(apiFetch("/documents")).rejects.toBeInstanceOf(ApiError)
    expect(restricted).toHaveBeenCalledOnce()
    window.removeEventListener("cognate-access-restricted", restricted)
  })

  it("marks API requests as non-cacheable", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        new Response(JSON.stringify({ ok: true }), { status: 200 }),
      )
    const { apiFetch } = await import("../services/api")
    await apiFetch("/auth/me")
    expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({
      credentials: "include",
      cache: "no-store",
    })
  })

  it("completes MFA through the pending login challenge endpoint", async () => {
    document.cookie = "mdis_csrf=synthetic-csrf; path=/"
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          user: {
            id: "user-1",
            email: "synthetic@example.test",
            display_name: null,
            role: "admin",
          },
        }),
        { status: 200 },
      ),
    )
    const { loginWithMfa } = await import("../services/api")
    const result = await loginWithMfa("", "", "123456")
    expect(result.role).toBe("admin")
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain(
      "/auth/mfa/verify-login",
    )
    expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({
      method: "POST",
      credentials: "include",
      cache: "no-store",
    })
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({
      code: "123456",
    })
  })

  it("surfaces the backend MFA-pending response so the login UI can request the challenge code", async () => {
    document.cookie = "mdis_csrf=synthetic-csrf; path=/"
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ ready: true }), { status: 200 }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            status: "pending_mfa",
            message: "Additional verification is required.",
            mfa_required: true,
          }),
          { status: 200 },
        ),
      )
    const { login } = await import("../services/api")
    await expect(
      login("synthetic@example.test", "synthetic password 123", true),
    ).rejects.toMatchObject({
      status: 202,
      message: "API 202: MFA verification required",
    })
  })
})
