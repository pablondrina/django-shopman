import { beforeEach, describe, expect, it } from "vitest";

import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { useShowcaseBoard } from "../../app/composables/useShowcaseBoard";

const env = installNuxtGlobals();

describe("useShowcaseBoard", () => {
  beforeEach(() => env.reset());

  it("deriva board da projection", () => {
    env.fetchData.value = { board: { showcases: [{ ref: "menu" }] } };
    expect(useShowcaseBoard().board.value).toEqual({ showcases: [{ ref: "menu" }] });
  });

  it("setActive/setCollections postam url + body corretos", async () => {
    const s = useShowcaseBoard();
    await s.setActive("menu-1", true);
    let [url, opts] = env.fetchMock.mock.calls[0]!;
    expect(String(url)).toBe("/api/v1/backstage/showcases/active/");
    expect(opts.body).toEqual({ ref: "menu-1", is_active: true });

    await s.setCollections("menu-1", ["c1", "c2"]);
    [url, opts] = env.fetchMock.mock.calls[1]!;
    expect(String(url)).toBe("/api/v1/backstage/showcases/collections/");
    expect(opts.body).toEqual({ ref: "menu-1", collections: ["c1", "c2"] });
  });

  it("guarda de reentrância por-ref", async () => {
    let release!: () => void;
    env.fetchMock.mockReturnValueOnce(new Promise<void>((r) => { release = r; }));
    const s = useShowcaseBoard();
    const first = s.setActive("m", true);
    expect(s.isBusy("m")).toBe(true);
    expect(await s.setActive("m", false)).toBe(false);
    expect(env.fetchMock).toHaveBeenCalledTimes(1);
    release();
    await first;
    expect(s.isBusy("m")).toBe(false);
  });

  it("falha acende errorMsg + toast e devolve false", async () => {
    env.fetchMock.mockRejectedValueOnce({ data: { detail: "Feed bloqueado" } });
    const s = useShowcaseBoard();
    expect(await s.setActive("m", true)).toBe(false);
    expect(s.errorMsg.value).toBe("Feed bloqueado");
    expect(env.sonner.error).toHaveBeenCalledWith("Feed bloqueado");
  });
});
