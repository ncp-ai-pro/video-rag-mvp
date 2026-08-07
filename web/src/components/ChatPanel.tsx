import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Play } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { fetchChatHistory, streamChat } from '@/lib/chat'
import { formatTimestamp, playbackUrl, youtubeIdFromUrl } from '@/lib/format'
import type { ChatMessage, Evidence, EvidenceMode } from '@/lib/types'

/**
 * 한 번의 질문·답변·근거. 대화는 백엔드(GET /chat/history)에 작업공간별로 저장된다.
 * assistant 메시지에는 저장된 근거(evidence)가 함께 돌아오므로, 새로고침 후에도 다시 렌더링할 수 있다.
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
  let pendingId: number | null = null
  const push = (question: string, answer: string, evidence: Evidence[] = []) =>
    turns.push({ id: pendingId !== null ? `message-${pendingId}` : crypto.randomUUID(), question, answer, evidence, status: 'done' })

  for (const message of messages) {
    if (message.role === 'user') {
      if (pendingQuestion !== null) push(pendingQuestion, '')
      pendingQuestion = message.content
      pendingId = message.id
    } else {
      push(pendingQuestion ?? '', message.content, message.evidence ?? [])
      pendingQuestion = null
      pendingId = null
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
  const [evidenceMode, setEvidenceMode] = useState<EvidenceMode>('simple')
  const [historyCursor, setHistoryCursor] = useState<number | null>(null)
  const [historyHasMore, setHistoryHasMore] = useState(false)
  const [historyLoading, setHistoryLoading] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const preserveScrollHeightRef = useRef<number | null>(null)
  const historyLoadingRef = useRef(false)

  const loadHistoryPage = useCallback(
    async ({ beforeId = null, prepend = false }: { beforeId?: number | null; prepend?: boolean } = {}) => {
      if (!workspaceCode || historyLoadingRef.current) return
      historyLoadingRef.current = true
      setHistoryLoading(true)
      if (prepend) preserveScrollHeightRef.current = scrollRef.current?.scrollHeight ?? null
      try {
        const page = await fetchChatHistory({ limit: 20, beforeId })
        const pageTurns = messagesToTurns(page.items)
        setHistoryCursor(page.next_cursor)
        setHistoryHasMore(page.has_more)
        setTurns((prev) => (prepend ? [...pageTurns, ...prev] : pageTurns))
      } catch {
        if (!prepend) setTurns([])
      } finally {
        historyLoadingRef.current = false
        setHistoryLoading(false)
      }
    },
    [workspaceCode],
  )

  // 작업공간 기준으로 저장된 대화 기록을 불러온다.
  useEffect(() => {
    if (!workspaceCode) {
      setTurns([])
      setHistoryCursor(null)
      setHistoryHasMore(false)
      return
    }
    setTurns([])
    setHistoryCursor(null)
    setHistoryHasMore(false)
    loadHistoryPage()
  }, [loadHistoryPage, workspaceCode])

  // 새 내용이 생기면 맨 아래로 스크롤한다.
  useLayoutEffect(() => {
    const container = scrollRef.current
    if (!container) return
    const previousHeight = preserveScrollHeightRef.current
    if (previousHeight !== null) {
      container.scrollTop = container.scrollHeight - previousHeight
      preserveScrollHeightRef.current = null
      return
    }
    container.scrollTo({ top: container.scrollHeight })
  }, [turns])

  const loadOlderHistory = () => {
    if (historyHasMore && historyCursor && !historyLoading) {
      void loadHistoryPage({ beforeId: historyCursor, prepend: true })
    }
  }

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
        { evidenceMode, signal: controller.signal, videoId },
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

  const quoteWithHighlight = (item: Evidence) => {
    const quote = item.quote
    const highlight = item.highlight?.text
    if (!highlight) return quote
    const index = quote.indexOf(highlight)
    if (index < 0) return quote
    return (
      <>
        {quote.slice(0, index)}
        <strong className="font-semibold text-foreground">{highlight}</strong>
        {quote.slice(index + highlight.length)}
      </>
    )
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-border/60 px-4 py-2.5">
        <span className="text-sm font-medium">대화</span>
        <span className="text-xs text-muted-foreground">작업공간에 저장됨</span>
      </div>

      {/* 대화 (백엔드 저장) */}
      <div
        ref={scrollRef}
        className="min-h-0 flex-1 space-y-5 overflow-y-auto p-4"
        onScroll={(event) => {
          if (event.currentTarget.scrollTop <= 24) loadOlderHistory()
        }}
      >
        {historyHasMore && (
          <div className="flex justify-center">
            <Button type="button" variant="ghost" size="sm" disabled={historyLoading} onClick={loadOlderHistory}>
              {historyLoading ? '불러오는 중…' : '이전 대화'}
            </Button>
          </div>
        )}

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
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <p className="text-[0.72rem] font-medium uppercase tracking-[0.08em] text-muted-foreground">
                      참고 구간
                    </p>
                    <p className="text-[0.72rem] text-muted-foreground">클릭하면 영상 위치로 이동</p>
                  </div>
                  <ul className="space-y-1.5">
                    {turn.evidence.map((item) => (
                      <li key={`${item.video_id}-${item.start_seconds}`}>
                        <button
                          type="button"
                          onClick={() => seekTo(item)}
                          className={`group w-full rounded-xl border px-3 py-2 text-left transition-colors hover:border-foreground/20 hover:bg-muted/40 ${
                            item.is_primary
                              ? 'border-foreground/15 bg-background shadow-[inset_2px_0_0_hsl(var(--foreground)/0.28)]'
                              : 'border-border/60 bg-background/70'
                          }`}
                        >
                          <div className="flex items-center gap-2 text-xs">
                            <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 font-mono text-[0.68rem] text-muted-foreground">
                              <Play className="size-3" />
                              {formatTimestamp(item.start_seconds)}–{formatTimestamp(item.end_seconds)}
                            </span>
                            {item.is_primary && (
                              <span className="rounded-full border border-border/70 px-1.5 py-0.5 text-[0.65rem] font-medium text-foreground/70">
                                주요
                              </span>
                            )}
                            <span className="min-w-0 truncate text-muted-foreground">{item.title}</span>
                          </div>
                          <p className="mt-1.5 line-clamp-2 text-xs leading-relaxed text-foreground/75">
                            {quoteWithHighlight(item)}
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
      <div className="border-t border-border/60 p-3">
        <div className="mb-2 flex items-center gap-2">
          <span className="text-xs text-muted-foreground">근거</span>
          <div className="inline-flex overflow-hidden rounded-full border border-border/70 bg-background">
            <Button
              type="button"
              variant="ghost"
              size="xs"
              className={`rounded-none px-3 ${evidenceMode === 'simple' ? 'bg-foreground text-background hover:bg-foreground/90 hover:text-background' : 'text-muted-foreground'}`}
              onClick={() => setEvidenceMode('simple')}
            >
              기본
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="xs"
              className={`rounded-none px-3 ${evidenceMode === 'precise' ? 'bg-foreground text-background hover:bg-foreground/90 hover:text-background' : 'text-muted-foreground'}`}
              onClick={() => setEvidenceMode('precise')}
            >
              문장 강조
            </Button>
          </div>
        </div>
        <form onSubmit={ask} className="flex gap-2">
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
    </div>
  )
}
