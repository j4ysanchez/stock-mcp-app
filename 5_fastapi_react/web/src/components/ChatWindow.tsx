import { useEffect, useRef } from 'react'
import type { Message } from '../App'
import ChatInput from './ChatInput'
import MessageBubble from './MessageBubble'
import styles from './ChatWindow.module.css'

interface Props {
  messages: Message[]
  streaming: boolean
  onSend: (text: string) => void
}

export default function ChatWindow({ messages, streaming, onSend }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  return (
    <div className={styles.root}>
      <header className={styles.header}>
        <h1>Stock Analyst</h1>
        <span className={styles.tickers}>
          AAPL · AMZN · GOOGL · META · MSFT · NFLX · NVDA · TSLA
        </span>
      </header>

      <div className={styles.messages}>
        {messages.length === 0 && (
          <p className={styles.empty}>Ask me anything about megacap tech stocks.</p>
        )}
        {messages.map((msg, i) => (
          <MessageBubble key={i} message={msg} />
        ))}
        <div ref={bottomRef} />
      </div>

      <ChatInput disabled={streaming} onSend={onSend} />
    </div>
  )
}
