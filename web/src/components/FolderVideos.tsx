import { useMemo, useState } from 'react'
import { Link2, Play, Plus, Rss } from 'lucide-react'

import { StatusBadge } from '@/components/StatusBadge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import { useFolderVideos } from '@/hooks/queries/folder/use-folder-videos'
import { useFolderCandidates } from '@/hooks/queries/folder/use-folder-candidates'
import { useAddFolderVideo } from '@/hooks/mutations/folder/use-add-folder-video'
import { useAnalyzeCandidate } from '@/hooks/mutations/folder/use-analyze-candidate'
import { useAddChannelSource } from '@/hooks/mutations/folder/use-add-channel-source'
import { formatUploadDate } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { FolderCandidate, FolderVideo } from '@/api/types'

interface Props {
  selectedFolderId: number | null
  selectedVideoId: number | null
  onSelectVideo: (video: FolderVideo) => void
  onError: (message: string) => void
}

function VideoRow({ video, active, onClick }: { video: FolderVideo; active: boolean; onClick: () => void }) {
  return (
    <li>
      <button
        type="button"
        onClick={onClick}
        className={cn(
          'flex w-full items-start gap-3 border-b border-border/40 px-3 py-2.5 text-left transition-colors hover:bg-accent',
          active && 'bg-accent',
        )}
      >
        {/* UnivAI 문서 카드처럼 썸네일을 앞에 둔다. thumbnail_url이 없으면 그라데이션 + 아이콘으로 대신한다. */}
        <span className="flex size-14 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-gradient-to-br from-primary/25 to-primary/5">
          {video.thumbnail_url ? (
            <img src={video.thumbnail_url} alt="" className="size-full object-cover" />
          ) : (
            <Play className="size-4 text-primary" />
          )}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <span className="line-clamp-2 text-sm">{video.title}</span>
            <StatusBadge status={video.analysis_status} />
          </div>
          <span className="mt-0.5 block text-[11px] text-muted-foreground">
            {formatUploadDate(video.added_at)}
          </span>
        </div>
      </button>
    </li>
  )
}

function CandidateRow({
  candidate,
  adding,
  onAdd,
}: {
  candidate: FolderCandidate
  adding: boolean
  onAdd: () => void
}) {
  return (
    <li className="border-b border-border/40 px-3 py-2.5">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="line-clamp-2 text-sm">{candidate.title}</p>
          <p className="mt-0.5 truncate text-[11px] text-muted-foreground">
            {candidate.source_label ?? '추천'}
            {candidate.score != null && ` · 유사도 ${candidate.score.toFixed(2)}`}
          </p>
        </div>
        <Button type="button" size="xs" variant="outline" disabled={adding} onClick={onAdd} className="shrink-0">
          {adding ? '추가 중…' : '분석 후 추가'}
        </Button>
      </div>
    </li>
  )
}

/**
 * 폴더 안 영상: 위쪽은 검색 + [폴더 영상]/[수집 후보] 두 섹션(탭 전환 없이 한 화면에서 스크롤).
 * "영상 추가"(URL 직접 추가 + 채널 연결)는 다이얼로그로 뺐다(작업공간 연결과 같은 패턴).
 * folder-first-api-spec.md 기준: 폴더 영상과 수집 후보는 서로 다른 API(폴더 영상 vs 후보)다 —
 * 후보는 아직 실제 영상이 아니라서 클릭 대신 "분석 후 추가" 버튼으로만 폴더에 들어온다.
 */
export function FolderVideos({ selectedFolderId, selectedVideoId, onSelectVideo, onError }: Props) {
  const { data: videos = [], isLoading: videosLoading } = useFolderVideos(selectedFolderId)
  const { data: candidates = [], isLoading: candidatesLoading } = useFolderCandidates(selectedFolderId)

  const addVideoMutation = useAddFolderVideo(selectedFolderId, {
    onError: () => onError('영상 추가에 실패했습니다.'),
  })
  const analyzeCandidateMutation = useAnalyzeCandidate(selectedFolderId, {
    onError: () => onError('후보를 폴더에 추가하지 못했습니다.'),
  })
  const addChannelSourceMutation = useAddChannelSource(selectedFolderId, {
    onError: () => onError('채널 연결에 실패했습니다.'),
  })

  const [filterText, setFilterText] = useState('')
  const [addOpen, setAddOpen] = useState(false)
  const [newVideoUrl, setNewVideoUrl] = useState('')
  const [channelUrl, setChannelUrl] = useState('')
  const [analyzingCandidateId, setAnalyzingCandidateId] = useState<number | null>(null)

  const filteredVideos = useMemo(() => {
    const text = filterText.trim().toLowerCase()
    return text ? videos.filter((video) => video.title.toLowerCase().includes(text)) : videos
  }, [videos, filterText])

  const addVideo = (event: React.FormEvent) => {
    event.preventDefault()
    if (!newVideoUrl.trim() || selectedFolderId === null) return
    addVideoMutation.mutate(newVideoUrl.trim(), {
      onSuccess: () => setNewVideoUrl(''),
    })
  }

  const connectChannel = (event: React.FormEvent) => {
    event.preventDefault()
    if (!channelUrl.trim() || selectedFolderId === null) return
    addChannelSourceMutation.mutate(channelUrl.trim(), {
      onSuccess: () => setChannelUrl(''),
    })
  }

  const addCandidate = (candidate: FolderCandidate) => {
    setAnalyzingCandidateId(candidate.id)
    analyzeCandidateMutation.mutate(candidate.id, {
      onSettled: () => setAnalyzingCandidateId(null),
    })
  }

  if (selectedFolderId === null) {
    return (
      <div className="flex h-full items-center justify-center p-4 text-xs text-muted-foreground">
        폴더를 선택하세요.
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col">
      {/* 검색 + 영상 추가(다이얼로그) */}
      <div className="flex items-center gap-1.5 border-b border-border/60 p-3">
        <Input
          value={filterText}
          placeholder="폴더 내 영상 검색"
          aria-label="폴더 내 영상 검색"
          className="flex-1"
          onChange={(event) => setFilterText(event.target.value)}
        />
        <Dialog open={addOpen} onOpenChange={setAddOpen}>
          <DialogTrigger asChild>
            <Button type="button" variant="outline" size="icon-sm" aria-label="영상 추가">
              <Plus />
            </Button>
          </DialogTrigger>
          <DialogContent className="sm:max-w-2xl">
            <DialogHeader>
              <DialogTitle>영상 추가</DialogTitle>
              <DialogDescription>URL을 직접 넣거나, 채널을 연결해서 새 영상을 자동으로 수집합니다.</DialogDescription>
            </DialogHeader>

            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-3 rounded-xl border border-border/60 bg-card/40 p-4">
                <div className="flex items-center gap-2.5">
                  <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary/15 text-primary">
                    <Link2 className="size-4" />
                  </span>
                  <div>
                    <p className="text-sm font-medium">URL로 추가</p>
                    <p className="text-[11px] text-muted-foreground">영상 링크 하나를 바로 넣습니다</p>
                  </div>
                </div>
                <form onSubmit={addVideo} className="space-y-2">
                  <Input
                    type="url"
                    required
                    value={newVideoUrl}
                    placeholder="https://youtube.com/watch?v=..."
                    aria-label="새 영상 URL"
                    onChange={(event) => setNewVideoUrl(event.target.value)}
                  />
                  <Button
                    type="submit"
                    className="w-full"
                    disabled={addVideoMutation.isPending || !newVideoUrl.trim()}
                  >
                    {addVideoMutation.isPending ? '추가 중…' : '추가'}
                  </Button>
                </form>
              </div>

              <div className="space-y-3 rounded-xl border border-border/60 bg-card/40 p-4">
                <div className="flex items-center gap-2.5">
                  <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary/15 text-primary">
                    <Rss className="size-4" />
                  </span>
                  <div>
                    <p className="text-sm font-medium">채널·재생목록 연결</p>
                    <p className="text-[11px] text-muted-foreground">
                      새 영상을 찾아 수집 후보로 추천 (채널·재생목록 URL 둘 다 가능)
                    </p>
                  </div>
                </div>
                <form onSubmit={connectChannel} className="space-y-2">
                  <Input
                    type="url"
                    required
                    value={channelUrl}
                    placeholder="채널 또는 재생목록 URL"
                    aria-label="연결할 채널·재생목록 URL"
                    onChange={(event) => setChannelUrl(event.target.value)}
                  />
                  <Button
                    type="submit"
                    variant="outline"
                    className="w-full"
                    disabled={addChannelSourceMutation.isPending || !channelUrl.trim()}
                  >
                    {addChannelSourceMutation.isPending ? '연결 중…' : '연결'}
                  </Button>
                </form>
              </div>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      {/* 목록: 탭 전환 없이 폴더 영상 → 수집 후보 순으로 한 화면에서 스크롤만으로 다 본다. */}
      <ScrollArea className="min-h-0 flex-1">
        {videosLoading ? (
          <div className="space-y-2 p-3">
            {[0, 1, 2].map((key) => (
              <Skeleton key={key} className="h-12 w-full" />
            ))}
          </div>
        ) : filteredVideos.length === 0 ? (
          <p className="p-4 text-xs text-muted-foreground">
            영상이 없습니다. 위 "+"에서 URL로 추가하거나 채널을 연결하세요.
          </p>
        ) : (
          <ul>
            {filteredVideos.map((video) => (
              <VideoRow
                key={video.id}
                video={video}
                active={video.id === selectedVideoId}
                onClick={() => onSelectVideo(video)}
              />
            ))}
          </ul>
        )}

        {!candidatesLoading && candidates.length > 0 && (
          <div>
            <p className="bg-background/95 px-3 py-1.5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground backdrop-blur">
              수집 후보 · {candidates.length}
            </p>
            <ul>
              {candidates.map((candidate) => (
                <CandidateRow
                  key={candidate.id}
                  candidate={candidate}
                  adding={analyzingCandidateId === candidate.id}
                  onAdd={() => addCandidate(candidate)}
                />
              ))}
            </ul>
          </div>
        )}
      </ScrollArea>
    </div>
  )
}
