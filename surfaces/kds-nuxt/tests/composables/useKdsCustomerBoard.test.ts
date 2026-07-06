import { beforeEach, describe, expect, it } from "vitest";
import { installNuxtGlobals } from "../support/composableEnv";
import { useKdsCustomerBoard } from "~/composables/useKdsCustomerBoard";

const env = installNuxtGlobals();

describe("useKdsCustomerBoard — public pickup board", () => {
  beforeEach(() => env.reset());

  it("derives the preparing/ready status from the public payload", () => {
    env.fetchData.value = {
      status: {
        preparing: [{ ref: "WEB-0007", status: "preparing", status_label: "Preparando", updated_at_display: "08:00" }],
        ready: [{ ref: "WEB-0006", status: "ready", status_label: "Pronto", updated_at_display: "07:58" }],
        updated_at_display: "08:00",
      },
    };
    const { status } = useKdsCustomerBoard();
    expect(status.value?.preparing).toHaveLength(1);
    expect(status.value?.ready).toHaveLength(1);
  });

  it("degrades to null when there is no payload (never throws on the public TV)", () => {
    env.fetchData.value = null;
    expect(useKdsCustomerBoard().status.value).toBeNull();
  });
});
