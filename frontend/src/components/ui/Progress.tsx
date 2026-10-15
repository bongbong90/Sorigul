interface ProgressProps {
  value: number
  max?: number
  label?: string
}

export function Progress({ value, max = 100, label }: ProgressProps) {
  const clamped = Math.min(Math.max(value, 0), max)
  const percent = (clamped / max) * 100

  return (
    <div
      className="progress"
      role="progressbar"
      aria-valuenow={clamped}
      aria-valuemin={0}
      aria-valuemax={max}
      aria-label={label}
    >
      <div className="progress-fill" style={{ width: `${percent}%` }} />
    </div>
  )
}
