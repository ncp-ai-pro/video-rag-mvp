import { Badge } from '@/components/ui/badge'
import { STATUS_LABEL } from '@/lib/format'
import { isAnalysisActive, isAnalyzed, type AnalysisStatus } from '@/api/types'

const variantFor = (status: AnalysisStatus) => {
  if (isAnalyzed(status)) return 'default' as const
  if (status === 'failed') return 'destructive' as const
  if (isAnalysisActive(status)) return 'secondary' as const
  return 'outline' as const
}

export function StatusBadge({ status }: { status: AnalysisStatus }) {
  return (
    <Badge variant={variantFor(status)} className="shrink-0">
      {STATUS_LABEL[status] ?? status}
    </Badge>
  )
}
