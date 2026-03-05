import { useRef, useState } from 'react'
import { sendMessage, type SSEEvent } from './api'
import ChatWindow from './components/ChatWindow'

export type ToolCall = { name: string; args: Record<string, unknown> }

export type Message = {
  role: 'user' | 'assistant'
  text: string
  toolCalls: ToolCall[]
}

const SESSION_ID = crypto.randomUUID()

export default function App() {
  const [messages, setMessages] = useState<Message[]>([])
  const [streaming, setStreaming] = useState(false)
  const pendingRef = useRef<Message | null>(null)

  async function handleSend(text: string) {
    setMessages((prev) => [...prev, { role: 'user', text, toolCalls: [] }])
    setStreaming(true)

    const assistant: Message = { role: 'assistant', text: '', toolCalls: [] }
    pendingRef.current = assistant
    setMessages((prev) => [...prev, assistant])

    function onEvent(e: SSEEvent) {
      if (e.type === 'tool_call') {
        const updated = {
          ...pendingRef.current!,
          toolCalls: [...pendingRef.current!.toolCalls, { name: e.name, args: e.args }],
        }
        pendingRef.current = updated
        setMessages((prev) => [...prev.slice(0, -1), updated])
      } else if (e.type === 'text') {
        const updated = { ...pendingRef.current!, text: e.text }
        pendingRef.current = updated
        setMessages((prev) => [...prev.slice(0, -1), updated])
      } else if (e.type === 'done') {
        setStreaming(false)
        pendingRef.current = null
      } else if (e.type === 'error') {
        const updated = { ...pendingRef.current!, text: `Error: ${e.message}` }
        pendingRef.current = null
        setMessages((prev) => [...prev.slice(0, -1), updated])
        setStreaming(false)
      }
    }

    try {
      await sendMessage(text, SESSION_ID, onEvent)
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      const updated = { ...pendingRef.current!, text: `Error: ${msg}` }
      pendingRef.current = null
      setMessages((prev) => [...prev.slice(0, -1), updated])
      setStreaming(false)
    }
  }

  return <ChatWindow messages={messages} streaming={streaming} onSend={handleSend} />
}
