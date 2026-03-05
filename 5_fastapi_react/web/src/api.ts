export type SSEEvent =
  | { type: 'tool_call'; name: string; args: Record<string, unknown> }
  | { type: 'text'; text: string }
  | { type: 'done' }
  | { type: 'error'; message: string }

export async function sendMessage(
  message: string,
  sessionId: string,
  onEvent: (e: SSEEvent) => void,
): Promise<void> {
  const res = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, session_id: sessionId }),
  })

  if (!res.ok) {
    throw new Error(`HTTP ${res.status}: ${res.statusText}`)
  }

  const reader = res.body!.getReader()
  const dec = new TextDecoder()
  let buf = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += dec.decode(value, { stream: true })
    const parts = buf.split('\n\n')
    buf = parts.pop() ?? ''
    for (const part of parts) {
      if (!part.startsWith('data: ')) continue
      const event = JSON.parse(part.slice(6)) as SSEEvent
      onEvent(event)
    }
  }
}
