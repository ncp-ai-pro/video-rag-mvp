import { forwardRef, useImperativeHandle, useRef } from 'react'
import YouTube, { type YouTubePlayer, type YouTubeProps } from 'react-youtube'

/** 근거 클릭 시 App이 호출하는 명령형 핸들. */
export interface PlayerHandle {
  /** 지정한 영상을 불러와 해당 시점부터 재생한다(다른 영상이어도 됨). */
  playAt: (youtubeId: string, seconds: number) => void
}

const OPTS: YouTubeProps['opts'] = {
  width: '100%',
  height: '100%',
  playerVars: {
    rel: 0,
    modestbranding: 1,
    cc_load_policy: 1, // 자막 기본 표시
    hl: 'ko',
  },
}

interface Props {
  /**
   * 사이드바에서 선택한 영상. react-youtube가 이 prop 변경을 감지해
   * 내부적으로 안전하게 cueVideoById를 호출한다(직접 호출하면 마운트 중 크래시).
   */
  youtubeId: string
}

export const Player = forwardRef<PlayerHandle, Props>(function Player({ youtubeId }, ref) {
  const playerRef = useRef<YouTubePlayer | null>(null)
  const pendingSeekRef = useRef<{ id: string; seconds: number } | null>(null)

  useImperativeHandle(ref, () => ({
    playAt(id, seconds) {
      if (playerRef.current) {
        playerRef.current.loadVideoById({ videoId: id, startSeconds: seconds })
      } else {
        // 아직 준비 전이면 onReady에서 처리한다.
        pendingSeekRef.current = { id, seconds }
      }
    },
  }))

  const onReady: YouTubeProps['onReady'] = (event) => {
    playerRef.current = event.target
    if (pendingSeekRef.current) {
      const { id, seconds } = pendingSeekRef.current
      pendingSeekRef.current = null
      event.target.loadVideoById({ videoId: id, startSeconds: seconds })
    }
  }

  return (
    <div className="aspect-video w-full overflow-hidden rounded-xl border border-border/60 bg-black">
      <YouTube
        videoId={youtubeId}
        opts={OPTS}
        onReady={onReady}
        className="h-full w-full"
        iframeClassName="h-full w-full"
      />
    </div>
  )
})
