import { describe, expect, it } from "vitest"

import { formatBytes, formatCount, formatSeconds } from "./format"

describe("format", () => {
  it("affiche les durées en secondes", () => {
    expect(formatSeconds(1234)).toBe("1.2 s")
  })

  it("abrège les grands nombres", () => {
    expect(formatCount(512)).toBe("512")
    expect(formatCount(40960)).toBe("41K")
    expect(formatCount(1_048_576)).toBe("1M")
  })

  it("affiche les tailles comme Ollama", () => {
    expect(formatBytes(5_225_388_164)).toBe("5.2 GB")
    expect(formatBytes(274_302_450)).toBe("274 MB")
    expect(formatBytes(900)).toBe("900 B")
  })
})
