import { afterEach, describe, expect, it, vi } from "vitest"

describe("cookie-based authentication client", () => {
  afterEach(() => {
    vi.restoreAllMocks()
    document.cookie = "mdis_csrf=; Max-Age=0; path=/"
  })

  it("bootstraps CSRF, sends login credentials with cookies, and stores no auth token in Web Storage", async () => {
    document.cookie = "mdis_csrf=synthetic-csrf-value; path=/"
    const user = {
      id: "user-1",
      email: "clinician@example.test",
      display_name: "Synthetic User",
      role: "clinician",
    }
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ ready: true }), { status: 200 }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ user }), { status: 200 }),
      )
    const { login, getAccessToken } = await import("../services/api")

    await expect(login(user.email, "synthetic passphrase")).resolves.toEqual(
      user,
    )

    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ credentials: "include" })
    const loginInit = fetchMock.mock.calls[1][1]
    expect(loginInit?.credentials).toBe("include")
    expect(new Headers(loginInit?.headers).get("X-CSRF-Token")).toBe(
      "synthetic-csrf-value",
    )
    expect(loginInit?.body).toBe(
      JSON.stringify({
        email: user.email,
        password: "synthetic passphrase",
        remember_me: false,
      }),
    )
    expect(getAccessToken()).toBeNull()
    expect(sessionStorage.length).toBe(0)
    expect(localStorage.length).toBe(0)
  })
})
