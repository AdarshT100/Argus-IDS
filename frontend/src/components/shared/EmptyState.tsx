import { Alert } from '../ui/alert'

type EmptyStateProps = {
  text: string
}

export function EmptyState({ text }: EmptyStateProps) {
  return <Alert>{text}</Alert>
}
