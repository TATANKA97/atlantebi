import { describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

const service = await import("./service");

describe("semantic column sensitivity classification", () => {
  it("marks credential material as non-queryable sensitive metadata", () => {
    expect(service.classifyColumnSensitivity("PasswordHash")).toEqual({
      kind: "credential",
      reason: "credential_name"
    });
    expect(service.classifyColumnSensitivity("PasswordSalt")).toEqual({
      kind: "credential",
      reason: "credential_name"
    });
    expect(service.classifyColumnSensitivity("ApiKey")).toEqual({
      kind: "credential",
      reason: "secret_key_name"
    });
  });

  it("marks direct contact fields as PII", () => {
    expect(service.classifyColumnSensitivity("EmailAddress")).toEqual({
      kind: "pii",
      reason: "contact_identifier"
    });
    expect(service.classifyColumnSensitivity("Phone")).toEqual({
      kind: "pii",
      reason: "contact_identifier"
    });
    expect(service.classifyColumnSensitivity("FirstName")).toEqual({
      kind: "pii",
      reason: "direct_person_identifier"
    });
    expect(service.classifyColumnSensitivity("AddressLine1")).toEqual({
      kind: "pii",
      reason: "direct_person_identifier"
    });
  });

  it("does not classify ordinary BI identifiers as secrets", () => {
    expect(service.classifyColumnSensitivity("ProductCategoryID")).toEqual({
      kind: "none"
    });
    expect(service.classifyColumnSensitivity("CustomerID")).toEqual({
      kind: "none"
    });
  });
});
