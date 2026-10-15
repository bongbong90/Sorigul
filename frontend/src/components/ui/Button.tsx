import type { ButtonHTMLAttributes } from 'react'

type ButtonVariant = 'primary' | 'secondary'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
}

export function Button({ variant = 'primary', className, ...props }: ButtonProps) {
  const variantClass = variant === 'primary' ? 'btn-primary' : 'btn-secondary'
  return (
    <button
      type="button"
      className={['btn', variantClass, className].filter(Boolean).join(' ')}
      {...props}
    />
  )
}
