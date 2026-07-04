import { afterEach, describe, expect, it, vi } from "vitest";
import { buildClientErrorReport, reportClientError } from "../app/utils/clientErrorReport";

describe("buildClientErrorReport", () => {
  it("reduces an Error to an allow-listed report", () => {
    const report = buildClientErrorReport(new Error("kaboom"), { source: "vue", app_version: "1.2.3" });
    expect(report).toMatchObject({ message: "kaboom", source: "vue", app_version: "1.2.3" });
  });

  it("clamps long message/stack/url and falls back to 'unknown error'", () => {
    const long = "x".repeat(1000);
    const report = buildClientErrorReport({}, { message: long, stack: long, url: long });
    expect(report.message.length).toBe(500);
    expect(report.stack?.length).toBe(4000 > long.length ? long.length : 4000);
    expect(report.url?.length).toBe(300);
    expect(buildClientErrorReport(undefined).message).toBe("unknown error");
  });
});

describe("reportClientError", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("POSTs the report to the backstage endpoint via the BFF", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true });
    vi.stubGlobal("$fetch", fetchMock);
    await expect(reportClientError(new Error("boom"), { source: "promise" })).resolves.toBe(true);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/backstage/client-error/",
      expect.objectContaining({ method: "POST", body: expect.objectContaining({ message: "boom" }) }),
    );
  });

  it("is silent when telemetry itself fails (never a visible error)", async () => {
    vi.stubGlobal("$fetch", vi.fn().mockRejectedValue(new Error("network")));
    await expect(reportClientError(new Error("boom"))).resolves.toBe(false);
  });
});
