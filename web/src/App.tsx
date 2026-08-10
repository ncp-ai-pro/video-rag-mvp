import { useCallback, useEffect, useRef, useState } from 'react'
import { Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import { toast, Toaster } from 'sonner'

import { Footer } from '@/components/Footer'
import { Header } from '@/components/Header'
import type { PlayerHandle } from '@/components/Player'
import { HomePage } from '@/pages/HomePage'
import { WorkspacePage } from '@/pages/WorkspacePage'
import { useAnalysisEvents } from '@/hooks/useAnalysisEvents'
import { api } from '@/lib/api'
import {
  isAnalysisActive,
  type AnalysisEvent,
  type Channel,
  type Video,
  type Workspace,
} from '@/lib/types'

const errorMessage = (error: unknown, fallback: string) =>
  error instanceof Error ? error.message : fallback

export default function App() {
  const [workspace, setWorkspace] = useState<Workspace | null>(null)
  const [channels, setChannels] = useState<Channel[]>([])
  const [selectedChannelId, setSelectedChannelId] = useState<number | null>(null)
  const [videos, setVideos] = useState<Video[]>([])
  const [videosLoading, setVideosLoading] = useState(false)
  const [selectedVideoId, setSelectedVideoId] = useState<number | null>(null)

  const playerRef = useRef<PlayerHandle>(null)
  const navigate = useNavigate()
  const selectedVideo = videos.find((video) => video.id === selectedVideoId) ?? null

  const showError = useCallback((message: string) => toast.error(message), [])

  const loadChannels = useCallback(async () => {
    try {
      const list = await api.listChannels()
      setChannels(list)
      setSelectedChannelId((current) => current ?? list[0]?.id ?? null)
      return list
    } catch (error) {
      showError(errorMessage(error, '채널 목록을 불러오지 못했습니다.'))
      return []
    }
  }, [showError])

  const loadVideos = useCallback(
    async (channelId: number) => {
      setVideosLoading(true)
      try {
        setVideos(await api.listVideos(channelId))
      } catch (error) {
        showError(errorMessage(error, '영상 목록을 불러오지 못했습니다.'))
      } finally {
        setVideosLoading(false)
      }
    },
    [showError],
  )

  // 최초 진입: 서버 상태 → 작업공간 → 채널.
  useEffect(() => {
    void (async () => {
      try {
        await api.health()
        setWorkspace(await api.me())
        await loadChannels()
      } catch (error) {
        showError(errorMessage(error, '서버에 연결하지 못했습니다.'))
      }
    })()
  }, [loadChannels, showError])

  useEffect(() => {
    if (selectedChannelId === null) {
      setVideos([])
      return
    }
    setSelectedVideoId(null)
    void loadVideos(selectedChannelId)
  }, [selectedChannelId, loadVideos])

  const applyAnalysisEvent = useCallback((event: AnalysisEvent) => {
    setVideos((current) =>
      current.map((video) =>
        video.id === event.video_id
          ? {
              ...video,
              analysis_status: event.status,
              analysis_stage: event.progress.stage,
              analysis_message: event.progress.message,
              analysis_error: event.error,
              analysis_updated_at: event.updated_at,
            }
          : video,
      ),
    )
  }, [])

  const watchedVideoId =
    selectedVideo && isAnalysisActive(selectedVideo.analysis_status) ? selectedVideo.id : null

  useAnalysisEvents(watchedVideoId, applyAnalysisEvent)

  const replaceWorkspace = async (next: Workspace) => {
    setWorkspace(next)
    setSelectedChannelId(null)
    setSelectedVideoId(null)
    setVideos([])
    setChannels([])
    await loadChannels()
  }

  const handleConnectWorkspace = async (code: string) => {
    try {
      await replaceWorkspace(await api.connectWorkspace(code))
      toast.success('기존 작업공간에 연결했습니다.')
    } catch (error) {
      showError(errorMessage(error, '작업공간 연결에 실패했습니다.'))
    }
  }

  const handleNewWorkspace = async () => {
    const confirmed = window.confirm(
      '새 작업공간으로 전환할까요? 현재 작업공간은 코드로 다시 연결할 수 있습니다.',
    )
    if (!confirmed) return
    try {
      const next = await api.newWorkspace()
      await replaceWorkspace(next)
      toast.success(`새 작업공간 ${next.workspace_code}을 만들었습니다.`)
    } catch (error) {
      showError(errorMessage(error, '새 작업공간을 만들지 못했습니다.'))
    }
  }

  // 채널 등록 + 자동 스캔. 홈과 사이드바 '추가'가 공유한다.
  const handleAddChannel = async (url: string) => {
    try {
      const channel = await api.createChannel(url)
      setSelectedChannelId(channel.id)
      await loadChannels()
      await api.scanChannel(channel.id)
      toast.success('채널을 등록하고 영상 탐색을 시작했습니다. 잠시 후 목록에 나타납니다.')
    } catch (error) {
      showError(errorMessage(error, '채널 등록에 실패했습니다.'))
      throw error
    }
  }

  const handleScan = async () => {
    if (selectedChannelId === null) return
    try {
      const job = await api.scanChannel(selectedChannelId)
      toast.success(`영상 탐색 작업 ${job.job_id}번을 등록했습니다.`)
    } catch (error) {
      showError(errorMessage(error, '탐색 작업 등록에 실패했습니다.'))
    }
  }

  const handleAnalyze = async () => {
    if (!selectedVideo) return
    try {
      const job = await api.analyzeVideo(selectedVideo.id)
      toast.success(`분석 작업 ${job.job_id}번을 등록했습니다.`)
      applyAnalysisEvent({
        video_id: selectedVideo.id,
        job_id: job.job_id,
        status: 'queued',
        progress: { stage: 'queued', message: '분석 작업을 기다리고 있습니다.' },
        error: null,
        updated_at: null,
      })
    } catch (error) {
      showError(errorMessage(error, '분석 작업 등록에 실패했습니다.'))
    }
  }

  const handleSeek = (youtubeId: string, seconds: number) => {
    playerRef.current?.playAt(youtubeId, seconds)
  }

  // 홈에서 채널을 눌러 바로 작업 환경으로 진입한다.
  const openChannelInWorkspace = (channelId: number) => {
    setSelectedChannelId(channelId)
    navigate('/workspace')
  }

  return (
    // 뷰포트 높이에 고정하고 넘침을 막아, 안쪽 패널들이 각자 스크롤하게 한다.
    <div className="flex h-dvh flex-col overflow-hidden bg-background text-foreground">
      <Header
        workspace={workspace}
        onConnect={handleConnectWorkspace}
        onCreateNew={handleNewWorkspace}
      />

      <Routes>
        <Route
          path="/"
          element={
            <HomePage
              channels={channels}
              onSubmit={handleAddChannel}
              onOpenChannel={openChannelInWorkspace}
            />
          }
        />
        <Route
          path="/workspace"
          element={
            <WorkspacePage
              channels={channels}
              selectedChannelId={selectedChannelId}
              onSelectChannel={setSelectedChannelId}
              onAddChannel={handleAddChannel}
              onScan={handleScan}
              videos={videos}
              videosLoading={videosLoading}
              selectedVideoId={selectedVideoId}
              onSelectVideo={(video) => setSelectedVideoId(video.id)}
              selectedVideo={selectedVideo}
              playerRef={playerRef}
              onAnalyze={handleAnalyze}
              onSeek={handleSeek}
              onError={showError}
              workspaceCode={workspace?.workspace_code ?? null}
            />
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>

      <Footer />
      <Toaster position="bottom-center" richColors theme="dark" />
    </div>
  )
}
