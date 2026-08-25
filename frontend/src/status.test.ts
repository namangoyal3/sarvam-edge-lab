import { describe, it, expect } from "vitest";
import { statusColor } from "./ui";

describe("statusColor", () => {
  it("maps healthy statuses to green", () => {
    expect(statusColor("online")).toBe("green");
    expect(statusColor("completed")).toBe("green");
    expect(statusColor("compatible")).toBe("green");
    expect(statusColor("PASS")).toBe("green");
  });
  it("maps failure statuses to red", () => {
    expect(statusColor("rejected")).toBe("red");
    expect(statusColor("incompatible")).toBe("red");
    expect(statusColor("critical")).toBe("red");
  });
  it("maps attention statuses to amber", () => {
    expect(statusColor("queued_offline")).toBe("amber");
    expect(statusColor("needs_review")).toBe("amber");
    expect(statusColor("pending_sync")).toBe("amber");
  });
  it("falls back to gray for unknown", () => {
    expect(statusColor("something_else")).toBe("gray");
  });
});

describe("policy decision display contract", () => {
  // The four user-visible outcomes required by the product spec.
  it("exposes exactly the documented outcome vocabulary", () => {
    const outcomes = ["completed", "needs_review", "queued_offline", "rejected"];
    outcomes.forEach((o) => expect(statusColor(o)).not.toBe("gray"));
  });
});
