interface ProgressProps {
  value: number | null
  max?: number
  label?: string
}

export function Progress({ value, max = 100, label }: ProgressProps) {
  if (value === null) {
    return (
      <div className="progress progress-indeterminate" role="progressbar" aria-label={label}>
        <div className="progress-fill" />
      </div>
    )
  }
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
