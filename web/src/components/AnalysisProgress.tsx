import { Check, Loader2 } from 'lucide-react'

import { PROGRESS_STEPS, stageProgress, stepState } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { Video } from '@/api/types'

/** 분석 진행 중 화면. 백엔드 SSE stage를 목업의 스텝 UI로 보여준다. */
export function AnalysisProgress({ video }: { video: Video }) {
  const progress = stageProgress(video.analysis_stage)

  return (
    <div className="mx-auto w-full max-w-lg rounded-2xl border border-border/60 bg-card p-6 shadow-lg">
      <div className="flex items-center gap-4">
        <div className="grid size-16 shrink-0 place-items-center rounded-lg bg-muted">
          <Loader2 className="size-6 animate-spin text-primary" />
        </div>
        <div className="min-w-0">
          <p className="text-sm font-medium text-primary">분석 중</p>
          <p className="truncate font-medium">{video.title}</p>
        </div>
      </div>

      <div className="mt-5 h-2 w-full overflow-hidden rounded-full bg-muted">
        <div
          className="h-full rounded-full bg-primary transition-[width] duration-500"
          style={{ width: `${progress}%` }}
        />
      </div>

      <ul className="mt-6 space-y-4">
        {PROGRESS_STEPS.map((step) => {
          const state = stepState(step, video.analysis_stage)
          return (
            <li key={step.key} className="flex items-center gap-3">
              <span
                className={cn(
                  'grid size-6 shrink-0 place-items-center rounded-full border text-xs',
                  state === 'done' && 'border-primary bg-primary text-primary-foreground',
                  state === 'active' && 'border-primary text-primary',
                  state === 'pending' && 'border-border text-muted-foreground',
                )}
              >
                {state === 'done' ? (
                  <Check className="size-3.5" />
                ) : state === 'active' ? (
                  <Loader2 className="size-3.5 animate-spin" />
                ) : (
                  ''
                )}
              </span>
              <div>
                <p
                  className={cn(
                    'text-sm font-medium',
                    state === 'pending' && 'text-muted-foreground',
                  )}
                >
                  {step.label}
                </p>
                {state === 'active' && video.analysis_message && (
                  <p className="text-xs text-muted-foreground">{video.analysis_message}</p>
                )}
                {state === 'done' && <p className="text-xs text-muted-foreground">완료</p>}
              </div>
            </li>
          )
        })}
      </ul>

      <p className="mt-6 text-center text-xs text-muted-foreground">
        영상 길이에 따라 30초~2분 소요됩니다.
      </p>
    </div>
  )
}
