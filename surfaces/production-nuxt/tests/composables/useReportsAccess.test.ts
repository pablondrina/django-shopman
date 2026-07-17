import { beforeEach, describe, expect, it } from "vitest";
import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { useReportsAccess } from "~/composables/useReportsAccess";

const env = installNuxtGlobals();

describe("useReportsAccess", () => {
  beforeEach(() => env.reset());

  it("allows the nav entry when the manager API answers with a payload", () => {
    env.fetchData.value = { management: { selected_date: "2026-07-17" } };
    const { allowed } = useReportsAccess();
    expect(allowed.value).toBe(true);
  });

  it("hides the nav entry without a payload (floor operator, 403 probe)", () => {
    env.fetchData.value = null;
    const { allowed } = useReportsAccess();
    expect(allowed.value).toBe(false);
  });
});
