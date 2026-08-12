import { useLayoutEffect, useRef } from "react";
import { Play, Volume2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useChat } from "@/hooks/chat/use-chat";
import { useTts } from "@/hooks/chat/use-tts";
import { formatTimestamp, playbackUrl, youtubeIdFromUrl } from "@/lib/format";
import type { Evidence } from "@/api/types";
import { useExportChat } from "@/hooks/chat/use-export-chat";
import { useState } from "react";

interface Props {
  /** 작업공간이 바뀌면 그 작업공간의 대화 기록을 다시 불러온다. */
  workspaceCode: string | null;
  /** 선택된 영상 ID. 대화는 영상 단위로 저장·조회되므로 없으면 질문할 수 없다. */
  videoId: number | null;
  /** 선택된 영상 제목. 대화 대상 표시용이다. */
  videoTitle?: string | null;
  /** 근거 클릭 시 플레이어를 해당 영상·시점으로 이동시킨다. */
  onSeek: (youtubeId: string, seconds: number) => void;
  onError: (message: string) => void;
}

export function ChatPanel({ workspaceCode, videoId, videoTitle, onSeek, onError }: Props) {
  const {
    turns,
    query,
    setQuery,
    streaming,
    ask,
    canAsk,
    evidenceMode,
    setEvidenceMode,
    historyHasMore,
    historyLoading,
    loadOlderHistory,
  } = useChat(workspaceCode, videoId, onError);

  const scrollRef = useRef<HTMLDivElement>(null);
  const preserveScrollHeightRef = useRef<number | null>(null);
  const tts = useTts(onError);
  const { exportingFormat, exportChat } = useExportChat(onError);
  const [selectedTurnIds, setSelectedTurnIds] = useState<Set<string>>(new Set());

  const toggleTurnSelection = (turnId: string) => {
    setSelectedTurnIds((prev) => {
      const next = new Set(prev);
      if (next.has(turnId)) next.delete(turnId);
      else next.add(turnId);
      return next;
    });
  };

  const selectedMessageIds = Array.from(selectedTurnIds)
    .map((id) => (id.startsWith("message-") ? Number(id.slice("message-".length)) : null))
    .filter((id): id is number => id !== null);

  // 새 내용이 생기면 맨 아래로. 이전 대화를 앞에 붙였을 때는 보던 위치가 그대로 보이도록 높이를 보정한다.
  useLayoutEffect(() => {
    const container = scrollRef.current;
    if (!container) return;
    const previousHeight = preserveScrollHeightRef.current;
    if (previousHeight !== null) {
      container.scrollTop = container.scrollHeight - previousHeight;
      preserveScrollHeightRef.current = null;
      return;
    }
    container.scrollTo({ top: container.scrollHeight });
  }, [turns]);

  const loadOlder = () => {
    if (!historyHasMore || historyLoading) return;
    // fetchNextPage로 turns가 앞쪽에 늘어나기 전에, 지금 스크롤 높이를 기억해 둔다.
    preserveScrollHeightRef.current = scrollRef.current?.scrollHeight ?? null;
    loadOlderHistory();
  };

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    void ask(query);
  };

  const seekTo = (item: Evidence) => {
    const youtubeId = youtubeIdFromUrl(item.url);
    if (youtubeId) onSeek(youtubeId, item.start_seconds);
    else window.open(playbackUrl(item.url), "_blank", "noreferrer");
  };

  const quoteWithHighlight = (item: Evidence) => {
    const quote = item.quote;
    const highlight = item.highlight?.text;
    if (!highlight) return quote;
    const index = quote.indexOf(highlight);
    if (index < 0) return quote;
    return (
      <>
        {quote.slice(0, index)}
        <strong className="font-semibold text-foreground">{highlight}</strong>
        {quote.slice(index + highlight.length)}
      </>
    );
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-border/60 px-4 py-2.5">
        <span className="text-sm font-medium">대화</span>
        <span className="max-w-[66%] truncate text-xs text-muted-foreground">
          {videoTitle ? `질문 대상: ${videoTitle}` : "영상을 선택하세요"}
        </span>
      </div>

      {/* 대화 (백엔드 저장, 영상 단위) */}
      <div
        ref={scrollRef}
        className="min-h-0 flex-1 space-y-5 overflow-y-auto p-4"
        onScroll={(event) => {
          if (event.currentTarget.scrollTop <= 24) loadOlder();
        }}
      >
        {historyHasMore && (
          <div className="flex justify-center">
            <Button type="button" variant="ghost" size="sm" disabled={historyLoading} onClick={loadOlder}>
              {historyLoading ? "불러오는 중…" : "이전 대화"}
            </Button>
          </div>
        )}

        {turns.length === 0 && (
          <p className="text-sm text-muted-foreground">
            {canAsk
              ? "이 영상에서 분석된 자막 근거를 찾아 답합니다. 아래에 질문을 입력하세요."
              : "왼쪽 목록에서 질문할 영상을 먼저 선택하세요."}
          </p>
        )}

        {turns.map((turn, index) => {
          const isLast = index === turns.length - 1;
          return (
            <div key={turn.id} className="space-y-2">
              {/* 사용자 질문 */}
              <div className="flex justify-end">
                <button
                  type="button"
                  disabled={!turn.id.startsWith("message-")}
                  onClick={() => toggleTurnSelection(turn.id)}
                  className={`max-w-[85%] rounded-2xl rounded-tr-sm px-3 py-2 text-left text-sm text-primary-foreground transition-colors ${
                    selectedTurnIds.has(turn.id)
                      ? "bg-primary ring-2 ring-primary ring-offset-2 ring-offset-background"
                      : "bg-primary/80 hover:bg-primary"
                  }`}
                >
                  {turn.question}
                </button>
              </div>

              {/* AI 답변 */}
              {(turn.answer || turn.status === "streaming") && (
                <div className="rounded-2xl rounded-tl-sm bg-muted/50 px-3 py-2">
                  <p className="whitespace-pre-wrap text-sm leading-relaxed">
                    {turn.answer}
                    {isLast && streaming && turn.status === "streaming" && (
                      <span className="ml-0.5 animate-pulse">▍</span>
                    )}
                  </p>
                </div>
              )}

              {turn.status === "error" && (
                <p className="text-xs text-destructive">답변 생성에 실패했습니다.</p>
              )}

              {turn.status === "done" && turn.answer.trim() && (
                <div>
                  {tts.turnId === turn.id && tts.audioUrl ? (
                    <audio
                      controls
                      autoPlay
                      src={tts.audioUrl}
                      className="h-8 w-full"
                      onPlay={(event) => {
                        event.currentTarget.playbackRate = 1.5;
                      }}
                    />
                  ) : (
                    <Button
                      type="button"
                      variant="secondary"
                      size="xs"
                      disabled={tts.loading}
                      onClick={() => void tts.play(turn.id, turn.answer)}
                    >
                      <Volume2 />
                      {tts.loading && tts.turnId === turn.id ? "생성 중…" : "답변 듣기"}
                    </Button>
                  )}
                </div>
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
                              ? "border-foreground/15 bg-background shadow-[inset_2px_0_0_hsl(var(--foreground)/0.28)]"
                              : "border-border/60 bg-background/70"
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
          );
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
              className={`rounded-none px-3 ${evidenceMode === "simple" ? "bg-foreground text-background hover:bg-foreground/90 hover:text-background" : "text-muted-foreground"}`}
              onClick={() => setEvidenceMode("simple")}
            >
              기본
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="xs"
              className={`rounded-none px-3 ${evidenceMode === "precise" ? "bg-foreground text-background hover:bg-foreground/90 hover:text-background" : "text-muted-foreground"}`}
              onClick={() => setEvidenceMode("precise")}
            >
              문장 강조
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="xs"
              className={`rounded-none px-3 ${evidenceMode === "ultra" ? "bg-foreground text-background hover:bg-foreground/90 hover:text-background" : "text-muted-foreground"}`}
              onClick={() => setEvidenceMode("ultra")}
            >
              의미 강조
            </Button>
          </div>
        </div>
        <form onSubmit={submit} className="flex gap-2">
          <Input
            value={query}
            placeholder={canAsk ? "영상에 대해 질문하기" : "질문할 영상을 먼저 선택하세요"}
            aria-label="RAG 질문"
            disabled={!canAsk}
            onChange={(event) => setQuery(event.target.value)}
          />
          <Button type="submit" disabled={streaming || !canAsk || !query.trim()}>
            {streaming ? "생성 중…" : "질문"}
          </Button>
          <Button
  type="button"
  variant="ghost"
  size="sm"
  disabled={!videoId || turns.length === 0 || exportingFormat !== null}
  onClick={() => void exportChat(videoId, selectedMessageIds.length > 0 ? selectedMessageIds : undefined, "txt")}
>
  {exportingFormat === "txt" ? "내보내는 중…" : "TXT"}
</Button>
<Button
  type="button"
  variant="ghost"
  size="sm"
  disabled={!videoId || turns.length === 0 || exportingFormat !== null}
  onClick={() => void exportChat(videoId, selectedMessageIds.length > 0 ? selectedMessageIds : undefined, "pdf")}
>
  {exportingFormat === "pdf" ? "내보내는 중…" : "PDF"}
</Button>
        </form>
      </div>
    </div>
  );
}
