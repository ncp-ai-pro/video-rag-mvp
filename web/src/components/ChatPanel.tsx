import { useEffect, useRef, useState } from 'react'
import { Play } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { fetchChatHistory, streamChat } from '@/lib/chat'
import { formatTimestamp, playbackUrl, youtubeIdFromUrl } from '@/lib/format'
import type { ChatMessage, Evidence } from '@/lib/types'

/**
 * 한 번의 질문·답변·근거. 대화는 백엔드(GET /chat/history)에 작업공간별로 저장된다.
 * 서버는 텍스트만 저장하므로, 과거 turn에는 근거(evidence)가 없다(현재 세션 답변에만 있음).
 */
interface ChatTurn {
  id: string
  question: string
  answer: string
  evidence: Evidence[]
  status: 'streaming' | 'done' | 'error'
}

/** 서버의 평면 메시지 배열([user, assistant, ...])을 질문·답변 turn으로 묶는다. */
function messagesToTurns(messages: ChatMessage[]): ChatTurn[] {
  const turns: ChatTurn[] = []
  let pendingQuestion: string | null = null
  const push = (question: string, answer: string) =>
    turns.push({ id: crypto.randomUUID(), question, answer, evidence: [], status: 'done' })

  for (const message of messages) {
    if (message.role === 'user') {
      if (pendingQuestion !== null) push(pendingQuestion, '')
      pendingQuestion = message.content
    } else {
      push(pendingQuestion ?? '', message.content)
      pendingQuestion = null
    }
  }
  if (pendingQuestion !== null) push(pendingQuestion, '')
  return turns
}

interface Props {
  /** 작업공간이 바뀌면 그 작업공간의 대화 기록을 다시 불러온다. */
  workspaceCode: string | null
  /** 선택된 영상 ID. 있으면 그 영상으로 근거를 좁혀 질문한다. */
  videoId: number | null
  /** 근거 클릭 시 플레이어를 해당 영상·시점으로 이동시킨다. */
  onSeek: (youtubeId: string, seconds: number) => void
  onError: (message: string) => void
}

export function ChatPanel({ workspaceCode, videoId, onSeek, onError }: Props) {
  const [turns, setTurns] = useState<ChatTurn[]>([])
  const [query, setQuery] = useState('')
  const [streaming, setStreaming] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  // 작업공간 기준으로 저장된 대화 기록을 불러온다.
  useEffect(() => {
    if (!workspaceCode) {
      setTurns([])
      return
    }
    let cancelled = false
    fetchChatHistory()
      .then((messages) => {
        if (!cancelled) setTurns(messagesToTurns(messages))
      })
      .catch(() => {
        // 기록이 없거나 실패하면 빈 상태로 시작한다.
      })
    return () => {
      cancelled = true
    }
  }, [workspaceCode])

  // 새 내용이 생기면 맨 아래로 스크롤한다.
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight })
  }, [turns])

  const ask = async (event: React.FormEvent) => {
    event.preventDefault()
    const question = query.trim()
    if (!question || streaming) return

    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    const id = crypto.randomUUID()
    setQuery('')
    setStreaming(true)
    setTurns((prev) => [...prev, { id, question, answer: '', evidence: [], status: 'streaming' }])

    const patch = (fn: (turn: ChatTurn) => ChatTurn) =>
      setTurns((prev) => prev.map((turn) => (turn.id === id ? fn(turn) : turn)))

    try {
      await streamChat(
        question,
        (event) => {
          switch (event.type) {
            case 'evidence':
              patch((turn) => ({ ...turn, evidence: event.evidence }))
              break
            case 'token':
              patch((turn) => ({ ...turn, answer: turn.answer + event.text }))
              break
            case 'done':
              patch((turn) => ({ ...turn, evidence: event.evidence }))
              break
            case 'error':
              onError(event.message)
              patch((turn) => ({ ...turn, status: 'error' }))
              break
          }
        },
        { signal: controller.signal, videoId },
      )
      patch((turn) => (turn.status === 'streaming' ? { ...turn, status: 'done' } : turn))
    } catch (error) {
      if (controller.signal.aborted) return
      onError(error instanceof Error ? error.message : '질문 요청에 실패했습니다.')
      patch((turn) => ({ ...turn, status: 'error' }))
    } finally {
      setStreaming(false)
    }
  }

  const seekTo = (item: Evidence) => {
    const youtubeId = youtubeIdFromUrl(item.url)
    if (youtubeId) onSeek(youtubeId, item.start_seconds)
    else window.open(playbackUrl(item.url), '_blank', 'noreferrer')
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-border/60 px-4 py-2.5">
        <span className="text-sm font-medium">대화</span>
        <span className="text-xs text-muted-foreground">작업공간에 저장됨</span>
      </div>

      {/* 대화 (백엔드 저장) */}
      <div ref={scrollRef} className="min-h-0 flex-1 space-y-5 overflow-y-auto p-4">
        {turns.length === 0 && (
          <p className="text-sm text-muted-foreground">
            분석이 끝난 자막에서 근거를 찾아 답합니다. 아래에 질문을 입력하세요.
          </p>
        )}

        {turns.map((turn, index) => {
          const isLast = index === turns.length - 1
          return (
            <div key={turn.id} className="space-y-2">
              {/* 사용자 질문 */}
              <div className="flex justify-end">
                <p className="max-w-[85%] rounded-2xl rounded-tr-sm bg-primary px-3 py-2 text-sm text-primary-foreground">
                  {turn.question}
                </p>
              </div>

              {/* AI 답변 */}
              {(turn.answer || turn.status === 'streaming') && (
                <div className="rounded-2xl rounded-tl-sm bg-muted/50 px-3 py-2">
                  <p className="whitespace-pre-wrap text-sm leading-relaxed">
                    {turn.answer}
                    {isLast && streaming && turn.status === 'streaming' && (
                      <span className="ml-0.5 animate-pulse">▍</span>
                    )}
                  </p>
                </div>
              )}

              {turn.status === 'error' && (
                <p className="text-xs text-destructive">답변 생성에 실패했습니다.</p>
              )}

              {/* 근거 구간 */}
              {turn.evidence.length > 0 && (
                <div className="space-y-2">
                  <p className="text-xs font-medium text-muted-foreground">근거 구간</p>
                  <ul className="space-y-2">
                    {turn.evidence.map((item) => (
                      <li key={`${item.video_id}-${item.start_seconds}`}>
                        <button
                          type="button"
                          onClick={() => seekTo(item)}
                          className="group w-full rounded-lg border border-border/60 bg-card p-2.5 text-left transition-colors hover:border-primary/60 hover:bg-accent"
                        >
                          <div className="flex items-center gap-2">
                            <span className="grid size-7 shrink-0 place-items-center rounded-md bg-primary/15 text-primary group-hover:bg-primary group-hover:text-primary-foreground">
                              <Play className="size-3.5" />
                            </span>
                            <span className="truncate text-xs font-medium">{item.title}</span>
                            <span className="ml-auto shrink-0 font-mono text-xs text-muted-foreground">
                              {formatTimestamp(item.start_seconds)} – {formatTimestamp(item.end_seconds)}
                            </span>
                          </div>
                          <p className="mt-1.5 line-clamp-2 text-xs text-muted-foreground">
                            {item.quote}
                          </p>
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* 입력 */}
      <form onSubmit={ask} className="flex gap-2 border-t border-border/60 p-3">
        <Input
          value={query}
          placeholder="영상에 대해 질문하기"
          aria-label="RAG 질문"
          onChange={(event) => setQuery(event.target.value)}
        />
        <Button type="submit" disabled={streaming || !query.trim()}>
          {streaming ? '생성 중…' : '질문'}
        </Button>
      </form>
    </div>
  )
}
