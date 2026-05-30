import type { HTMLAttributes, ReactNode } from 'react'
import { cn } from '../../lib/utils'

type AlertVariant = 'info' | 'error'

type AlertProps = HTMLAttributes<HTMLDivElement> & {
  children: ReactNode
  variant?: AlertVariant
}

export function Alert({
  children,
  className,
  variant = 'info',
  ...props
}: AlertProps) {
  return (
    <div
      className={cn('ui-alert', `ui-alert-${variant}`, className)}
      role={variant === 'error' ? 'alert' : 'status'}
      {...props}
    >
      {children}
    </div>
  )
}
