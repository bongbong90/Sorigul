interface ProgressProps {
  value: number | null
  max?: number
  label?: string
}

export function Progress({ value, max = 100, label }: ProgressProps) {
  const normalizedMax = Number.isFinite(max) && max > 0 ? max : 100

  if (value === null) {
    return (
      <progress
        className="progress progress-indeterminate"
        max={normalizedMax}
        aria-label={label}
      />
    )
  }
  const clamped = Math.min(Math.max(value, 0), normalizedMax)

  return (
    <progress
      className="progress"
      value={clamped}
      max={normalizedMax}
      aria-label={label}
    />
  )
}
