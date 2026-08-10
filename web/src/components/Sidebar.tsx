import { useState } from 'react'
import { Plus, Search } from 'lucide-react'

import { StatusBadge } from '@/components/StatusBadge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import { api } from '@/lib/api'
import { formatUploadDate } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { Channel, Recommendation, Video } from '@/lib/types'

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
  onError: (message: string) => void
}

export function Sidebar({
  channels,
  selectedChannelId,
  onSelectChannel,
  onAddChannel,
  onScan,
  videos,
  videosLoading,
  selectedVideoId,
  onSelectVideo,
  onError,
}: Props) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<Recommendation[] | null>(null)
  const [searching, setSearching] = useState(false)

  const [addUrl, setAddUrl] = useState('')
  const [addOpen, setAddOpen] = useState(false)
  const [adding, setAdding] = useState(false)
  const [scanning, setScanning] = useState(false)

  const search = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!query.trim()) return
    setSearching(true)
    try {
      const result = await api.recommend(query.trim())
      setResults(result.items)
    } catch (error) {
      onError(error instanceof Error ? error.message : '추천 검색에 실패했습니다.')
    } finally {
      setSearching(false)
    }
  }

  const clearSearch = () => {
    setQuery('')
    setResults(null)
  }

  const pickRecommendation = (item: Recommendation) => {
    // 현재 채널 목록에 있으면 그 영상을 선택, 없으면 YouTube로 연다.
    const found = videos.find((video) => video.id === item.video_id)
    if (found) {
      onSelectVideo(found)
      clearSearch()
    } else {
      window.open(item.url, '_blank', 'noreferrer')
    }
  }

  const addChannel = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!addUrl.trim()) return
    setAdding(true)
    try {
      await onAddChannel(addUrl.trim())
      setAddUrl('')
      setAddOpen(false)
    } finally {
      setAdding(false)
    }
  }

  const scan = async () => {
    setScanning(true)
    try {
      await onScan()
    } finally {
      setScanning(false)
    }
  }

  return (
    <aside className="flex h-full flex-col gap-3 border-r border-border/60 bg-sidebar">
      {/* 추천 검색 */}
      <div className="space-y-2 p-3">
        <form onSubmit={search} className="relative">
          <Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            placeholder="영상 추천 검색"
            aria-label="영상 추천 검색"
            className="pl-8"
            onChange={(event) => setQuery(event.target.value)}
          />
        </form>

        {results !== null && (
          <div className="rounded-md border border-border/60 bg-card">
            <div className="flex items-center justify-between px-3 py-1.5 text-xs text-muted-foreground">
              <span>제목·설명 유사도 · {results.length}개</span>
              <button type="button" className="hover:text-foreground" onClick={clearSearch}>
                닫기
              </button>
            </div>
            {searching ? (
              <p className="px-3 pb-2 text-xs text-muted-foreground">검색 중…</p>
            ) : results.length === 0 ? (
              <p className="px-3 pb-2 text-xs text-muted-foreground">추천 결과가 없습니다.</p>
            ) : (
              <ul className="max-h-48 overflow-y-auto border-t border-border/60">
                {results.map((item) => (
                  <li key={item.video_id}>
                    <button
                      type="button"
                      onClick={() => pickRecommendation(item)}
                      className="w-full border-b border-border/40 px-3 py-2 text-left transition-colors last:border-0 hover:bg-accent"
                    >
                      <div className="flex items-baseline justify-between gap-2">
                        <span className="line-clamp-1 text-sm">{item.title}</span>
                        <span className="shrink-0 font-mono text-xs text-muted-foreground">
                          {item.score.toFixed(2)}
                        </span>
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>

      {/* 채널 선택 + 추가 */}
      <div className="space-y-2 px-3">
        <div className="flex items-center justify-between">
          <span className="text-xs font-medium text-muted-foreground">채널</span>
          <button
            type="button"
            className="flex items-center gap-1 text-xs text-primary hover:underline"
            onClick={() => setAddOpen((open) => !open)}
          >
            <Plus className="size-3.5" /> 추가
          </button>
        </div>

        {addOpen && (
          <form onSubmit={addChannel} className="flex gap-1.5">
            <Input
              type="url"
              required
              value={addUrl}
              placeholder="채널 URL"
              aria-label="채널 URL 추가"
              className="h-8 text-xs"
              onChange={(event) => setAddUrl(event.target.value)}
            />
            <Button type="submit" size="sm" className="h-8" disabled={adding || !addUrl.trim()}>
              등록
            </Button>
          </form>
        )}

        {channels.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {channels.map((channel) => (
              <button
                key={channel.id}
                type="button"
                onClick={() => onSelectChannel(channel.id)}
                className={cn(
                  'max-w-full truncate rounded-full border px-2.5 py-1 text-xs transition-colors',
                  channel.id === selectedChannelId
                    ? 'border-primary bg-primary/15 text-foreground'
                    : 'border-border/60 text-muted-foreground hover:bg-accent',
                )}
              >
                {channel.name || channel.url}
              </button>
            ))}
          </div>
        )}

        <Button
          variant="outline"
          size="sm"
          className="w-full"
          disabled={selectedChannelId === null || scanning}
          onClick={scan}
        >
          {scanning ? '탐색 등록 중…' : '새 영상 탐색'}
        </Button>
      </div>

      {/* 영상 목록 */}
      <ScrollArea className="min-h-0 flex-1 border-t border-border/60">
        {videosLoading ? (
          <div className="space-y-2 p-3">
            {[0, 1, 2].map((key) => (
              <Skeleton key={key} className="h-12 w-full" />
            ))}
          </div>
        ) : selectedChannelId === null ? (
          <p className="p-4 text-xs text-muted-foreground">채널을 선택하세요.</p>
        ) : videos.length === 0 ? (
          <p className="p-4 text-xs text-muted-foreground">
            영상이 없습니다. “새 영상 탐색”을 실행하세요.
          </p>
        ) : (
          <ul>
            {videos.map((video) => (
              <li key={video.id}>
                <button
                  type="button"
                  onClick={() => onSelectVideo(video)}
                  className={cn(
                    'w-full border-b border-border/40 px-3 py-2.5 text-left transition-colors hover:bg-accent',
                    video.id === selectedVideoId && 'bg-accent',
                  )}
                >
                  <div className="flex items-start justify-between gap-2">
                    <span className="line-clamp-2 text-sm">{video.title}</span>
                    <StatusBadge status={video.analysis_status} />
                  </div>
                  <span className="mt-0.5 block text-[11px] text-muted-foreground">
                    {formatUploadDate(video.uploaded_at)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </ScrollArea>
    </aside>
  )
}
