import type { HTMLAttributes } from 'react'

type BadgeTone =
  | 'waiting'
  | 'preparing'
  | 'transcribing'
  | 'saving'
  | 'done'
  | 'failed'
  | 'cancelled'

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone: BadgeTone
}

export function Badge({ tone, className, ...props }: BadgeProps) {
  return (
    <span
      className={['badge', `badge-${tone}`, className].filter(Boolean).join(' ')}
      {...props}
    />
  )
}
