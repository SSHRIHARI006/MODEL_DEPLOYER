import { describe, it, expect, beforeEach } from "vitest";
import { useStore } from "./store";

describe("useStore", () => {
  beforeEach(() => {
    localStorage.clear();
    useStore.getState().logout();
  });

  it("initializes with default empty state", () => {
    const state = useStore.getState();
    expect(state.token).toBeNull();
    expect(state.username).toBeNull();
    expect(state.wallet).toBeNull();
    expect(state.keys).toEqual([]);
    expect(state.theme).toBe("light");
  });

  it("updates auth and synchronizes with localStorage", () => {
    useStore.getState().setAuth("jwt-token-xyz", "alice");

    const state = useStore.getState();
    expect(state.token).toBe("jwt-token-xyz");
    expect(state.username).toBe("alice");
    expect(localStorage.getItem("token")).toBe("jwt-token-xyz");
    expect(localStorage.getItem("username")).toBe("alice");
  });

  it("clears auth and wallet on logout", () => {
    useStore.getState().setAuth("jwt-token-xyz", "alice");
    useStore.getState().logout();

    const state = useStore.getState();
    expect(state.token).toBeNull();
    expect(state.username).toBeNull();
    expect(state.wallet).toBeNull();
    expect(state.keys).toEqual([]);
    expect(localStorage.getItem("token")).toBeNull();
    expect(localStorage.getItem("username")).toBeNull();
  });

  it("toggles theme between light and dark", () => {
    expect(useStore.getState().theme).toBe("light");

    useStore.getState().toggleTheme();
    expect(useStore.getState().theme).toBe("dark");
    expect(localStorage.getItem("theme")).toBe("dark");

    useStore.getState().toggleTheme();
    expect(useStore.getState().theme).toBe("light");
    expect(localStorage.getItem("theme")).toBe("light");
  });
});
