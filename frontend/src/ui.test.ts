import { describe, it, expect } from "vitest";
import { fmtMs, fmtINR } from "./ui";

describe("fmtMs", () => {
  it("formats milliseconds under a second", () => {
    expect(fmtMs(62)).toBe("62ms");
  });
  it("formats seconds above a second", () => {
    expect(fmtMs(1250)).toBe("1.25s");
  });
  it("renders dash for null/undefined", () => {
    expect(fmtMs(null)).toBe("—");
    expect(fmtMs(undefined)).toBe("—");
  });
});

describe("fmtINR", () => {
  it("formats rupees with Indian grouping", () => {
    expect(fmtINR(18000)).toContain("18,000");
  });
  it("keeps small decimals", () => {
    expect(fmtINR(0.85)).toMatch(/0\.85/);
  });
});
