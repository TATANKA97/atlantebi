import { describe, expect, it, vi } from "vitest";

vi.mock("next/headers", () => ({
  cookies: vi.fn()
}));

import { safeNextPath } from "./route";

describe("auth callback redirect boundary", () => {
  it("allows only same-origin relative paths", () => {
    expect(safeNextPath("/connections")).toBe("/connections");
    expect(safeNextPath("/setup?created=1")).toBe("/setup?created=1");
    expect(safeNextPath("https://attacker.example")).toBe("/setup");
    expect(safeNextPath("//attacker.example")).toBe("/setup");
    expect(safeNextPath("/\\attacker.example")).toBe("/setup");
    expect(safeNextPath(null)).toBe("/setup");
  });
});
