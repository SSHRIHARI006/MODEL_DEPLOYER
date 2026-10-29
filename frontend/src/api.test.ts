import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";
import { api } from "./api";

describe("api client", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("adds Authorization header when token exists", async () => {
    localStorage.setItem("token", "secret-token-123");

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ success: true }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const res = await api.get<{ success: boolean }>("/test-path/");
    expect(res).toEqual({ success: true });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/test-path/",
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer secret-token-123",
          "Content-Type": "application/json",
        }),
      })
    );
  });

  it("handles 204 No Content gracefully returning undefined", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 204,
      json: async () => ({}),
    });
    vi.stubGlobal("fetch", fetchMock);

    const res = await api.delete("/keys/123/");
    expect(res).toBeUndefined();
  });

  it("throws error with message on non-ok status", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({ detail: "Invalid request payload" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(api.post("/test-err/", {})).rejects.toThrow("Invalid request payload");
  });

  // ---------------------------------------------------------------------------
  // UI-02: JWT Refresh Interceptor
  // ---------------------------------------------------------------------------

  it("refreshes expired token on 401 and retries original request once", async () => {
    localStorage.setItem("token", "expired-access-token");
    localStorage.setItem("refreshToken", "valid-refresh-token");

    const fetchMock = vi.fn()
      // 1. Initial request returns 401
      .mockResolvedValueOnce({
        ok: false,
        status: 401,
        json: async () => ({ detail: "Token expired" }),
      })
      // 2. Refresh request succeeds
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ access: "new-access-token", refresh: "new-refresh-token" }),
      })
      // 3. Retried original request succeeds with new token
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ data: "retried-success" }),
      });

    vi.stubGlobal("fetch", fetchMock);

    const res = await api.get<{ data: string }>("/protected-data/");
    expect(res).toEqual({ data: "retried-success" });
    expect(localStorage.getItem("token")).toBe("new-access-token");
    expect(localStorage.getItem("refreshToken")).toBe("new-refresh-token");
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("deduplicates concurrent 401 refresh calls into a single refresh request", async () => {
    localStorage.setItem("token", "expired-access-token");
    localStorage.setItem("refreshToken", "valid-refresh-token");

    let resolveRefresh: (val: any) => void;
    const refreshPromise = new Promise((resolve) => {
      resolveRefresh = resolve;
    });

    const fetchMock = vi.fn((url: string) => {
      if (url === "/api/auth/refresh/") {
        return refreshPromise;
      }
      if (url === "/api/req-1/" || url === "/api/req-2/") {
        // If it's called with new-token, succeed; else 401
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({ success: true }),
        });
      }
      return Promise.resolve({
        ok: false,
        status: 401,
        json: async () => ({ detail: "Expired" }),
      });
    });

    vi.stubGlobal("fetch", fetchMock);

    // Initial 401 responses for both concurrent calls
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 401,
      json: async () => ({ detail: "Expired" }),
    });
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 401,
      json: async () => ({ detail: "Expired" }),
    });

    const call1 = api.get("/req-1/");
    const call2 = api.get("/req-2/");

    // Resolve the single refresh call
    resolveRefresh!({
      ok: true,
      status: 200,
      json: async () => ({ access: "new-token" }),
    });

    const [res1, res2] = await Promise.all([call1, call2]);
    expect(res1).toEqual({ success: true });
    expect(res2).toEqual({ success: true });

    // Verify /api/auth/refresh/ was called exactly once
    const refreshCalls = fetchMock.mock.calls.filter((c) => c[0] === "/api/auth/refresh/");
    expect(refreshCalls.length).toBe(1);
  });
});
