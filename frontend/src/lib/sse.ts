export interface SSEMessage {
  event: string
  data: string
}

/**
 * Incremental Server-Sent Events parser.
 *
 * Network chunks can end anywhere (mid-line, even mid-word), so incomplete
 * input is buffered until a blank line closes the event.
 */
export class SSEParser {
  private buffer = ""

  feed(chunk: string): SSEMessage[] {
    this.buffer += chunk
    const blocks = this.buffer.split(/\r?\n\r?\n/)
    // The last block is either empty or an event still being received.
    this.buffer = blocks.pop() ?? ""
    return blocks.map(parseBlock).filter((message) => message !== null)
  }
}

function parseBlock(block: string): SSEMessage | null {
  let event = "message"
  const data: string[] = []

  for (const line of block.split(/\r?\n/)) {
    if (line === "" || line.startsWith(":")) continue // ":" starts a comment
    const colon = line.indexOf(":")
    const field = colon === -1 ? line : line.slice(0, colon)
    let value = colon === -1 ? "" : line.slice(colon + 1)
    if (value.startsWith(" ")) value = value.slice(1)

    if (field === "event") event = value
    else if (field === "data") data.push(value)
  }

  return data.length > 0 ? { event, data: data.join("\n") } : null
}
