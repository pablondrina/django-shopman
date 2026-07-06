import { nextTick, ref } from "vue";
import { beforeEach, describe, expect, it } from "vitest";
import { installNuxtGlobals } from "../support/composableEnv";
import { useBoardPages } from "~/composables/useBoardPages";

installNuxtGlobals();

const items = (n: number) => Array.from({ length: n }, (_, i) => i);

describe("useBoardPages — airport-panel pagination math", () => {
  beforeEach(() => {
    // ResizeObserver is only touched in onMounted (no-op here); a stub keeps setup safe.
    if (!(globalThis as Record<string, unknown>).ResizeObserver) {
      (globalThis as Record<string, unknown>).ResizeObserver = class {
        observe() {}
        disconnect() {}
      };
    }
  });

  it("splits items into fixed-size pages (default 8) and shows the current slice", () => {
    const source = ref(items(20));
    const { visible, pageCount, page } = useBoardPages(source);
    expect(pageCount.value).toBe(3); // ceil(20 / 8)
    expect(page.value).toBe(0);
    expect(visible.value).toEqual(items(8));
  });

  it("goTo wraps around both ends (a kiosk loop never dead-ends)", () => {
    const source = ref(items(20)); // 3 pages
    const { goTo, page } = useBoardPages(source);
    goTo(3); // 3 % 3 = 0
    expect(page.value).toBe(0);
    goTo(-1); // wraps to last page
    expect(page.value).toBe(2);
  });

  it("resets to the first page when the page count shrinks below the current page", async () => {
    const source = ref(items(20)); // 3 pages
    const { goTo, page } = useBoardPages(source);
    goTo(2);
    expect(page.value).toBe(2);
    source.value = items(4); // now 1 page
    await nextTick();
    expect(page.value).toBe(0);
  });

  it("always yields at least one page even when empty", () => {
    const { pageCount, visible } = useBoardPages(ref<number[]>([]));
    expect(pageCount.value).toBe(1);
    expect(visible.value).toEqual([]);
  });
});
