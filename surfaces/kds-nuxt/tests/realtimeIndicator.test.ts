import { describe, expect, it } from "vitest";
import { realtimeIndicator } from "../app/presentation/board";

describe("realtimeIndicator — honest live cue", () => {
  it("only 'live' is green + live=true (nunca uma bolinha verde mentirosa)", () => {
    const live = realtimeIndicator("live");
    expect(live.live).toBe(true);
    expect(live.dotClass).toContain("green");
  });

  it("'connecting' is amber and not live", () => {
    const c = realtimeIndicator("connecting");
    expect(c.live).toBe(false);
    expect(c.dotClass).toContain("amber");
  });

  it("'polling' is neutral, not live, and says it updates on its own", () => {
    const p = realtimeIndicator("polling");
    expect(p.live).toBe(false);
    expect(p.dotClass).not.toContain("green");
    expect(p.label.toLowerCase()).toContain("sozinho");
  });
});
