import { type Ref } from 'react'

import { ChatPanel } from '@/components/ChatPanel'
import { Sidebar } from '@/components/Sidebar'
import { VideoStage } from '@/components/VideoStage'
import type { PlayerHandle } from '@/components/Player'
import type { Channel, Video } from '@/lib/types'

interface Props {
  channels: Channel[]
  selectedChannelId: number | null
  onSelectChannel: (channelId: number) => void
  onAddChannel: (url: string) => Promise<void>
  onScan: () => Promise<void>
  videos: Video[]
  videosLoading: boolean
  selectedVideoId: number | null
  onSelectVideo: (video: Video) => void
  selectedVideo: Video | null
  playerRef: Ref<PlayerHandle>
  onAnalyze: () => Promise<void>
  onSeek: (youtubeId: string, seconds: number) => void
  onError: (message: string) => void
  workspaceCode: string | null
}

export function WorkspacePage({
  channels,
  selectedChannelId,
  onSelectChannel,
  onAddChannel,
  onScan,
  videos,
  videosLoading,
  selectedVideoId,
  onSelectVideo,
  selectedVideo,
  playerRef,
  onAnalyze,
  onSeek,
  onError,
  workspaceCode,
}: Props) {
  return (
    <main className="grid min-h-0 flex-1 grid-cols-1 overflow-y-auto lg:grid-cols-[300px_minmax(0,1fr)_360px] lg:overflow-hidden">
      <Sidebar
        channels={channels}
        selectedChannelId={selectedChannelId}
        onSelectChannel={onSelectChannel}
        onAddChannel={onAddChannel}
        onScan={onScan}
        videos={videos}
        videosLoading={videosLoading}
        selectedVideoId={selectedVideoId}
        onSelectVideo={onSelectVideo}
        onError={onError}
      />

      <section className="flex min-h-[60vh] flex-col p-4 lg:min-h-0 lg:overflow-y-auto">
        <VideoStage video={selectedVideo} playerRef={playerRef} onAnalyze={onAnalyze} />
      </section>

      {/* 데스크톱에선 min-h-0 + overflow-hidden으로 안쪽 대화가 스스로 스크롤하게 한다. */}
      <section className="flex min-h-0 flex-col border-t border-border/60 lg:h-full lg:overflow-hidden lg:border-l lg:border-t-0">
        <ChatPanel
          workspaceCode={workspaceCode}
          videoId={selectedVideo?.id ?? null}
          onSeek={onSeek}
          onError={onError}
        />
      </section>
    </main>
  )
}
