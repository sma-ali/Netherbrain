import { describe, expect, it } from "vitest"

import { SSEParser } from "./sse"

describe("SSEParser", () => {
  it("parses a complete event", () => {
    const parser = new SSEParser()

    expect(parser.feed('event: token\ndata: {"content":"Hi"}\n\n')).toEqual([
      { event: "token", data: '{"content":"Hi"}' },
    ])
  })

  it("buffers an event split across several chunks", () => {
    const parser = new SSEParser()

    expect(parser.feed("event: tok")).toEqual([])
    expect(parser.feed('en\ndata: {"content"')).toEqual([])
    expect(parser.feed(':"Hi"}\n\n')).toEqual([{ event: "token", data: '{"content":"Hi"}' }])
  })

  it("returns every event contained in one chunk", () => {
    const parser = new SSEParser()

    const messages = parser.feed("event: a\ndata: 1\n\nevent: b\ndata: 2\n\nevent: c\ndata: 3")

    expect(messages.map((m) => m.event)).toEqual(["a", "b"])
    expect(parser.feed("\n\n")).toEqual([{ event: "c", data: "3" }])
  })

  it("defaults the event name, joins multi-line data and skips comments", () => {
    const parser = new SSEParser()

    expect(parser.feed(": keep-alive\ndata: line 1\ndata: line 2\n\n")).toEqual([
      { event: "message", data: "line 1\nline 2" },
    ])
  })

  it("accepts CRLF line endings", () => {
    const parser = new SSEParser()

    expect(parser.feed("event: done\r\ndata: {}\r\n\r\n")).toEqual([{ event: "done", data: "{}" }])
  })
})
