export interface SSEMessage {
  event: string
  data: string
}

/**
 * Parseur incrémental de Server-Sent Events.
 *
 * Les morceaux reçus du réseau peuvent se couper n'importe où (en pleine ligne, voire en
 * plein mot) : ce qui est incomplet reste dans un tampon jusqu'à ce qu'une ligne vide
 * termine l'événement.
 */
export class SSEParser {
  private buffer = ""

  feed(chunk: string): SSEMessage[] {
    this.buffer += chunk
    const blocks = this.buffer.split(/\r?\n\r?\n/)
    // Le dernier bloc est soit vide, soit un événement encore en cours de réception.
    this.buffer = blocks.pop() ?? ""
    return blocks.map(parseBlock).filter((message) => message !== null)
  }
}

function parseBlock(block: string): SSEMessage | null {
  let event = "message"
  const data: string[] = []

  for (const line of block.split(/\r?\n/)) {
    if (line === "" || line.startsWith(":")) continue // ":" commence un commentaire
    const colon = line.indexOf(":")
    const field = colon === -1 ? line : line.slice(0, colon)
    let value = colon === -1 ? "" : line.slice(colon + 1)
    if (value.startsWith(" ")) value = value.slice(1)

    if (field === "event") event = value
    else if (field === "data") data.push(value)
  }

  return data.length > 0 ? { event, data: data.join("\n") } : null
}
