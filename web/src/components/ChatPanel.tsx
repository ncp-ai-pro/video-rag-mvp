import { useLayoutEffect, useRef, useState } from "react";
import { Volume2 } from "lucide-react";

import { AnalysisProgress } from "@/components/AnalysisProgress";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useExportChat } from "@/hooks/chat/use-export-chat";
import { useTts } from "@/hooks/chat/use-tts";
import type { UseChatResult } from "@/hooks/chat/use-chat";
import { isAnalysisActive, type FolderVideo } from "@/api/types";

interface Props {
  /** 대화 상태·동작은 WorkspacePage가 useChat으로 만들어 내려준다(EvidencePanel과 turns를 공유하기 위해). */
  chat: UseChatResult;
  /** 선택된 영상. 대화 대상 표시, 내보내기, 분석 진행 표시에 쓰인다. */
  video: FolderVideo | null;
  onError: (message: string) => void;
}

export function ChatPanel({ chat, video, onError }: Props) {
  const videoId = video?.id ?? null;
  const videoTitle = video?.title ?? null;
  const analyzing = video ? isAnalysisActive(video.analysis_status) : false;
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
  } = chat;

  const scrollRef = useRef<HTMLDivElement>(null);
  const preserveScrollHeightRef = useRef<number | null>(null);
  const tts = useTts(onError);
  const { exportingFormat, exportChat } = useExportChat(onError);
  const [selectedTurnIds, setSelectedTurnIds] = useState<Set<string>>(
    new Set(),
  );

  const toggleTurnSelection = (turnId: string) => {
    setSelectedTurnIds((prev) => {
      const next = new Set(prev);
      if (next.has(turnId)) next.delete(turnId);
      else next.add(turnId);
      return next;
    });
  };

  const selectedMessageIds = Array.from(selectedTurnIds)
    .map((id) =>
      id.startsWith("message-") ? Number(id.slice("message-".length)) : null,
    )
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

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-border/60 px-4 py-2.5">
        <span className="text-sm font-medium">대화</span>
        <span className="max-w-[66%] truncate text-xs text-muted-foreground">
          {videoTitle ? `질문 대상: ${videoTitle}` : "영상을 선택하세요"}
        </span>
      </div>

      {/* 선택한 영상이 분석 중이면, 우측 영상 자리 대신 여기(가운데)에서 진행 상황을 크게 보여준다. */}
      {analyzing && video ? (
        <div className="flex min-h-0 flex-1 items-center justify-center overflow-y-auto p-4">
          <AnalysisProgress video={video} />
        </div>
      ) : (
      /* 대화 (백엔드 저장, 영상 단위) */
      <div
        ref={scrollRef}
        className="min-h-0 flex-1 space-y-5 overflow-y-auto p-4"
        onScroll={(event) => {
          if (event.currentTarget.scrollTop <= 24) loadOlder();
        }}
      >
        {historyHasMore && (
          <div className="flex justify-center">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={historyLoading}
              onClick={loadOlder}
            >
              {historyLoading ? "불러오는 중…" : "이전 대화"}
            </Button>
          </div>
        )}

        {turns.length === 0 && (
          <p className="text-sm text-muted-foreground">
            {canAsk
              ? "이 영상에서 분석된 자막 근거를 찾아 답합니다. 아래에 질문을 입력하세요."
              : "영상 목록에서 질문할 영상을 먼저 선택하세요."}
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
                <p className="text-xs text-destructive">
                  답변 생성에 실패했습니다.
                </p>
              )}

              {turn.status === "done" && turn.answer.trim() && (
                <div className="flex items-center gap-2">
                  {tts.turnId === turn.id && tts.audioUrl ? (
                    <audio
                      controls
                      autoPlay
                      src={tts.audioUrl}
                      className="h-8 flex-1"
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
                      {tts.loading && tts.turnId === turn.id
                        ? "생성 중…"
                        : "답변 듣기"}
                    </Button>
                  )}

                  {/* 근거 상세는 채팅을 길게 만들지 않도록 오른쪽 근거 패널에서 보여준다.
                      이 배지는 몇 개인지만 알려준다(모바일엔 호버가 없어 클릭·호버 트리거 대신 이 편이 낫다). */}
                  {turn.evidence.length > 0 && (
                    <span className="text-[0.72rem] text-muted-foreground">
                      근거 {turn.evidence.length}개 → 오른쪽 패널
                    </span>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
      )}

      {/* 입력 */}
      <div className="border-t border-border/60 p-3">
        <div className="mb-2 flex flex-wrap items-center gap-x-4 gap-y-2">
          <div className="flex items-center gap-2">
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
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">음성</span>
            <div className="inline-flex overflow-hidden rounded-full border border-border/70 bg-background">
              <Button
                type="button"
                variant="ghost"
                size="xs"
                className={`rounded-none px-3 ${tts.voice === "nyounghwa" ? "bg-foreground text-background hover:bg-foreground/90 hover:text-background" : "text-muted-foreground"}`}
                onClick={() => tts.setVoice("nyounghwa")}
              >
                여성
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="xs"
                className={`rounded-none px-3 ${tts.voice === "njihun" ? "bg-foreground text-background hover:bg-foreground/90 hover:text-background" : "text-muted-foreground"}`}
                onClick={() => tts.setVoice("njihun")}
              >
                남성
              </Button>
            </div>
          </div>
        </div>
        <form onSubmit={submit} className="flex gap-2">
          <Input
            value={query}
            placeholder={
              canAsk ? "영상에 대해 질문하기" : "질문할 영상을 먼저 선택하세요"
            }
            aria-label="RAG 질문"
            disabled={!canAsk}
            onChange={(event) => setQuery(event.target.value)}
          />
          <Button
            type="submit"
            disabled={streaming || !canAsk || !query.trim()}
          >
            {streaming ? "생성 중…" : "질문"}
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={
              !videoId || turns.length === 0 || exportingFormat !== null
            }
            onClick={() =>
              void exportChat(
                videoId,
                selectedMessageIds.length > 0 ? selectedMessageIds : undefined,
                "txt",
              )
            }
          >
            {exportingFormat === "txt" ? "내보내는 중…" : "TXT"}
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={
              !videoId || turns.length === 0 || exportingFormat !== null
            }
            onClick={() =>
              void exportChat(
                videoId,
                selectedMessageIds.length > 0 ? selectedMessageIds : undefined,
                "pdf",
              )
            }
          >
            {exportingFormat === "pdf" ? "내보내는 중…" : "PDF"}
          </Button>
        </form>
      </div>
    </div>
  );
}
