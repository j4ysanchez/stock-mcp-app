import { useRef, useState } from 'react'
import styles from './ChatInput.module.css'

interface Props {
  disabled: boolean
  onSend: (text: string) => void
}

export default function ChatInput({ disabled, onSend }: Props) {
  const [value, setValue] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  function submit() {
    const text = value.trim()
    if (!text || disabled) return
    setValue('')
    if (textareaRef.current) textareaRef.current.style.height = 'auto'
    onSend(text)
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  function handleChange(e: React.ChangeEvent<HTMLTextAreaElement>) {
    setValue(e.target.value)
    const el = e.target
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`
  }

  return (
    <div className={styles.row}>
      <textarea
        ref={textareaRef}
        className={styles.input}
        rows={1}
        value={value}
        disabled={disabled}
        placeholder={disabled ? 'Thinking…' : 'Ask about a stock…'}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
      />
      <button
        className={styles.btn}
        disabled={disabled || !value.trim()}
        onClick={submit}
      >
        Send
      </button>
    </div>
  )
}
