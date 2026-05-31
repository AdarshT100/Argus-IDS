import { Skeleton } from '../ui/skeleton'

export function LoadingState() {
  return (
    <div className="loading-stack" aria-label="Loading backend data">
      <Skeleton />
      <Skeleton className="short" />
      <Skeleton className="medium" />
    </div>
  )
}
