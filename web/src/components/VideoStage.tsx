import { type Ref } from 'react'
import { Loader2, MonitorPlay, PlayCircle } from 'lucide-react'

import { ErrorBoundary } from '@/components/ErrorBoundary'
import { Player, type PlayerHandle } from '@/components/Player'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { formatDuration, formatUploadDate } from '@/lib/format'
import { isAnalysisActive, isAnalyzed, isMetadataPending, type Video } from '@/api/types'

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
          <p className="text-sm">영상 목록에서 선택하면 여기에 재생됩니다.</p>
        </div>
      </div>
    )
  }

  // URL만 접수되고 아직 yt-dlp로 metadata(제목·썸네일)도 못 가져온 상태.
  // 분석 파이프라인 이전 단계라 "분석 시작" CTA를 보여주지 않는다(중복 요청 방지 겸 의미 없음).
  if (isMetadataPending(video.analysis_status)) {
    return (
      <div className="flex flex-1 flex-col gap-3">
        <div className="flex aspect-video w-full flex-col items-center justify-center gap-2 rounded-xl border border-border/60 bg-muted/30 p-4 text-center">
          <Loader2 className="size-8 animate-spin text-primary" />
          <p className="text-sm font-medium">영상 정보를 가져오는 중…</p>
        </div>
      </div>
    )
  }

  // 전체 분석 진행 UI는 가운데 채팅 패널에서 보여준다(이 패널은 폭이 좁아 잘려 보였다).
  // 여기는 재생 영역 자리만 스피너로 대신 채워 레이아웃이 흔들리지 않게 한다.
  if (isAnalysisActive(video.analysis_status)) {
    return (
      <div className="flex flex-1 flex-col gap-3">
        <div className="flex aspect-video w-full flex-col items-center justify-center gap-2 rounded-xl border border-border/60 bg-muted/30 p-4 text-center">
          <Loader2 className="size-8 animate-spin text-primary" />
          <p className="text-sm font-medium">분석 중</p>
          <p className="line-clamp-2 text-xs text-muted-foreground">
            {video.analysis_message ?? '잠시만 기다려주세요.'}
          </p>
        </div>
        <div>
          <p className="font-medium leading-snug">{video.title}</p>
        </div>
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
