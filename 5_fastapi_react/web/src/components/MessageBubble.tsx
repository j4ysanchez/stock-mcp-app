import type { Message } from '../App'
import ToolCallBadge from './ToolCallBadge'
import styles from './MessageBubble.module.css'

interface Props {
  message: Message
}

export default function MessageBubble({ message }: Props) {
  const isUser = message.role === 'user'

  return (
    <div className={`${styles.bubble} ${isUser ? styles.user : styles.assistant}`}>
      {message.toolCalls.length > 0 && (
        <div className={styles.tools}>
          {message.toolCalls.map((tc, i) => (
            <ToolCallBadge key={i} name={tc.name} args={tc.args} />
          ))}
        </div>
      )}
      <p className={styles.text}>{message.text || (isUser ? '' : '…')}</p>
    </div>
  )
}
