import { useId, type InputHTMLAttributes } from 'react'

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string
  helperText?: string
  error?: boolean
}

export function Input({ label, helperText, error, id, className, ...props }: InputProps) {
  const generatedId = useId()
  const inputId = id ?? generatedId

  return (
    <div className="input-field">
      {label && (
        <label className="input-label text-label" htmlFor={inputId}>
          {label}
        </label>
      )}
      <input
        id={inputId}
        className={['input', error ? 'input-error' : '', className].filter(Boolean).join(' ')}
        aria-invalid={error || undefined}
        {...props}
      />
      {helperText && (
        <p className={['input-helper', error ? 'input-helper-error' : ''].filter(Boolean).join(' ')}>
          {helperText}
        </p>
      )}
    </div>
  )
}
