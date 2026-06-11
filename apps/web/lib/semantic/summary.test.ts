import { describe, expect, it } from "vitest";

import { coverageWarningsLabel } from "./summary";

describe("coverage warning summary", () => {
  it("distinguishes warning instances from grouped warning codes", () => {
    expect(coverageWarningsLabel(12, 3)).toBe(
      "Coverage warnings: 12 total, 3 grouped"
    );
  });
});
