import styles from './ToolCallBadge.module.css'

interface Props {
  name: string
  args: Record<string, unknown>
}

export default function ToolCallBadge({ name, args }: Props) {
  const argsStr = Object.entries(args)
    .map(([k, v]) => `${k}: ${String(v)}`)
    .join(', ')

  return (
    <span className={styles.badge} title={JSON.stringify(args, null, 2)}>
      {name}({argsStr})
    </span>
  )
}
