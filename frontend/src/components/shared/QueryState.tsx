import type { ReactNode } from 'react'
import { Alert } from '../ui/alert'
import { errorMessage } from '../../lib/utils'
import { EmptyState } from './EmptyState'
import { LoadingState } from './LoadingState'

type QueryStateProps = {
  isLoading: boolean
  error: unknown
  empty: boolean
  emptyText: string
  children: ReactNode
}

export function QueryState({
  isLoading,
  error,
  empty,
  emptyText,
  children,
}: QueryStateProps) {
  if (isLoading) {
    return <LoadingState />
  }

  if (error) {
    return <Alert variant="error">{errorMessage(error)}</Alert>
  }

  if (empty) {
    return <EmptyState text={emptyText} />
  }

  return children
}
