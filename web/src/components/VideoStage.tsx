import { type Ref } from 'react'
import { MonitorPlay, PlayCircle } from 'lucide-react'

import { AnalysisProgress } from '@/components/AnalysisProgress'
import { ErrorBoundary } from '@/components/ErrorBoundary'
import { Player, type PlayerHandle } from '@/components/Player'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { formatDuration, formatUploadDate } from '@/lib/format'
import { isAnalysisActive, isAnalyzed, type Video } from '@/api/types'

interface Props {
  video: Video | null
  playerRef: Ref<PlayerHandle>
  onAnalyze: () => Promise<void>
}

export function VideoStage({ video, playerRef, onAnalyze }: Props) {
  if (!video) {
    return (
      <div className="grid flex-1 place-items-center text-center text-muted-foreground">
        <div className="space-y-3">
          <PlayCircle className="mx-auto size-10 opacity-40" />
          <p className="text-sm">왼쪽에서 영상을 선택하면 여기에 재생됩니다.</p>
        </div>
      </div>
    )
  }

  if (isAnalysisActive(video.analysis_status)) {
    return (
      <div className="grid flex-1 place-items-center">
        <AnalysisProgress video={video} />
      </div>
    )
  }

  if (isAnalyzed(video.analysis_status)) {
    return (
      <div className="flex flex-1 flex-col gap-3">
        {/* key로 영상이 바뀌면 boundary도 초기화되어, 한 영상에서 죽어도 다음 영상은 정상. */}
        <ErrorBoundary
          key={video.platform_video_id}
          fallback={
            <div className="grid aspect-video w-full place-items-center rounded-xl border border-border/60 bg-black text-center text-sm text-muted-foreground">
              <div className="space-y-2 p-4">
                <p>이 영상을 웹에서 재생할 수 없습니다.</p>
                <a
                  href={video.url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-block text-primary underline-offset-4 hover:underline"
                >
                  YouTube에서 열기
                </a>
              </div>
            </div>
          }
        >
          <Player ref={playerRef} youtubeId={video.platform_video_id} />
        </ErrorBoundary>
        <div>
          <p className="font-medium leading-snug">{video.title}</p>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {formatUploadDate(video.uploaded_at)}
            {formatDuration(video.duration_seconds) ? ` · ${formatDuration(video.duration_seconds)}` : ''}
          </p>
        </div>
      </div>
    )
  }

  // 미분석 / 실패 → 분석 시작 CTA
  const failed = video.analysis_status === 'failed'
  return (
    <div className="grid flex-1 place-items-center">
      <div className="w-full max-w-md space-y-4 rounded-2xl border border-border/60 bg-card p-6 text-center">
        <MonitorPlay className="mx-auto size-10 text-muted-foreground" />
        <div>
          <p className="font-medium">{video.title}</p>
          <p className="mt-1 text-xs text-muted-foreground">
            {failed ? '분석에 실패했습니다. 다시 시도할 수 있습니다.' : '아직 분석하지 않은 영상입니다.'}
          </p>
        </div>

        {video.analysis_error && (
          <Alert variant="destructive" className="text-left">
            <AlertTitle>분석 실패</AlertTitle>
            <AlertDescription className="break-words">{video.analysis_error}</AlertDescription>
          </Alert>
        )}

        <Button className="w-full" onClick={onAnalyze}>
          {failed ? '다시 분석 시작' : '이 영상 분석 시작'}
        </Button>
        <a
          href={video.url}
          target="_blank"
          rel="noreferrer"
          className="block text-xs text-muted-foreground underline-offset-4 hover:underline"
        >
          YouTube에서 열기
        </a>
      </div>
    </div>
  )
}
