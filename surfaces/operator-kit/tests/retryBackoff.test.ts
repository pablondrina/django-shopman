import { describe, expect, it, vi } from "vitest";
import { retryWithBackoff } from "../app/utils/retryBackoff";

const noSleep = () => Promise.resolve();
const noJitter = () => 0;

describe("retryWithBackoff", () => {
  it("returns immediately on success without retrying", async () => {
    const fn = vi.fn().mockResolvedValue("ok");
    await expect(retryWithBackoff(fn, { sleep: noSleep, jitter: noJitter })).resolves.toBe("ok");
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it("retries transient errors up to `attempts` then resolves", async () => {
    const fn = vi
      .fn()
      .mockRejectedValueOnce({ status: 503 })
      .mockRejectedValueOnce({ status: 502 })
      .mockResolvedValue("recovered");
    await expect(retryWithBackoff(fn, { attempts: 3, sleep: noSleep, jitter: noJitter })).resolves.toBe("recovered");
    expect(fn).toHaveBeenCalledTimes(3);
  });

  it("does NOT retry a non-transient error (fail-loud)", async () => {
    const fn = vi.fn().mockRejectedValue({ status: 409 });
    await expect(retryWithBackoff(fn, { sleep: noSleep, jitter: noJitter })).rejects.toMatchObject({ status: 409 });
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it("propagates the last error after exhausting attempts", async () => {
    const fn = vi.fn().mockRejectedValue({ status: 503 });
    await expect(retryWithBackoff(fn, { attempts: 2, sleep: noSleep, jitter: noJitter })).rejects.toMatchObject({
      status: 503,
    });
    expect(fn).toHaveBeenCalledTimes(2);
  });

  it("applies exponential backoff with cap (delays observed by injected sleep)", async () => {
    const delays: number[] = [];
    const sleep = (ms: number) => {
      delays.push(ms);
      return Promise.resolve();
    };
    const fn = vi.fn().mockRejectedValue({ status: 503 });
    await expect(
      retryWithBackoff(fn, { attempts: 4, baseDelayMs: 100, capMs: 250, sleep, jitter: noJitter }),
    ).rejects.toBeTruthy();
    // 100, 200, min(250, 400)=250 — teto respeitado.
    expect(delays).toEqual([100, 200, 250]);
  });
});
