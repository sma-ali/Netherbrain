import { describe, expect, it } from "vitest"

import { parseDiff } from "./diff"

describe("parseDiff", () => {
  it("numbers each line on the side where it exists", () => {
    const rows = parseDiff(["@@ -4,3 +4,3 @@", " x = 1", "-print(1)", "+print(2)", " y = 2"])

    expect(rows.map((row) => [row.kind, row.oldLine, row.newLine, row.text])).toEqual([
      ["hunk", null, null, "@@ -4,3 +4,3 @@"],
      ["context", 4, 4, "x = 1"],
      ["remove", 5, null, "print(1)"],
      ["add", null, 5, "print(2)"],
      ["context", 6, 6, "y = 2"],
    ])
  })

  it("restarts the numbers at each block", () => {
    const rows = parseDiff(["@@ -1 +1,2 @@", " a", "+b", "@@ -40 +41 @@", "-z"])

    expect(rows.at(-1)).toEqual({ kind: "remove", text: "z", oldLine: 40, newLine: null })
  })

  it("starts a new file at line 1", () => {
    const rows = parseDiff(["@@ -0,0 +1,2 @@", "+first", "+second"])

    expect(rows.slice(1).map((row) => row.newLine)).toEqual([1, 2])
  })
})
