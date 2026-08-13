import { type Ref } from "react";
import { Play } from "lucide-react";

import { VideoStage } from "@/components/VideoStage";
import type { PlayerHandle } from "@/components/Player";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { UseChatResult } from "@/hooks/chat/use-chat";
import { STATUS_LABEL, formatDuration, formatTimestamp, playbackUrl, youtubeIdFromUrl } from "@/lib/format";
import type { Evidence, Video } from "@/api/types";

interface Props {
  video: Video | null;
  playerRef: Ref<PlayerHandle>;
  onAnalyze: () => Promise<void>;
  /** 채팅과 같은 turns를 공유해서, 마지막 답변의 근거를 자동으로 보여준다(호버 대신 항상 동기화). */
  chat: UseChatResult;
  onSeek: (youtubeId: string, seconds: number) => void;
}

/**
 * 형광펜 효과. 배경·글씨색을 라이트/다크 테마와 무관하게 고정한다(실제 형광펜처럼).
 * 이전엔 text-foreground를 썼는데, 다크모드에서 흰 글씨가 노란 배경 위에서 안 보였고,
 * 그라데이션 stop(40%/40%)이 겹쳐서 경계에 브라우저마다 다른 색 번짐이 생겼다.
 */
function quoteWithHighlight(item: Evidence) {
  const quote = item.quote;
  const highlight = item.highlight?.text;
  if (!highlight) return quote;
  const index = quote.indexOf(highlight);
  if (index < 0) return quote;
  return (
    <>
      {quote.slice(0, index)}
      <mark className="rounded-[2px] bg-yellow-300 px-0.5 text-yellow-950">
        {highlight}
      </mark>
      {quote.slice(index + highlight.length)}
    </>
  );
}

/** 우측 패널: 영상 + 마지막 답변의 근거. 답변이 새로 오면 자동으로 갱신된다. */
export function EvidencePanel({ video, playerRef, onAnalyze, chat, onSeek }: Props) {
  const lastTurn = chat.turns.length > 0 ? chat.turns[chat.turns.length - 1] : null;
  const evidence = lastTurn?.evidence ?? [];

  const seekTo = (item: Evidence) => {
    const youtubeId = youtubeIdFromUrl(item.url);
    if (youtubeId) onSeek(youtubeId, item.start_seconds);
    else window.open(playbackUrl(item.url), "_blank", "noreferrer");
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-col gap-3 border-b border-border/60 p-3">
        <VideoStage video={video} playerRef={playerRef} onAnalyze={onAnalyze} />

        {video && (
          <div className="grid grid-cols-3 divide-x divide-border/60 overflow-hidden rounded-lg border border-border/60 text-center">
            <div className="p-2">
              <p className="text-sm font-semibold">{formatDuration(video.duration_seconds) ?? "-"}</p>
              <p className="text-[10px] text-muted-foreground">길이</p>
            </div>
            <div className="p-2">
              <p className="text-sm font-semibold">{evidence.length}</p>
              <p className="text-[10px] text-muted-foreground">근거</p>
            </div>
            <div className="p-2">
              <p className="text-sm font-semibold">{STATUS_LABEL[video.analysis_status] ?? video.analysis_status}</p>
              <p className="text-[10px] text-muted-foreground">상태</p>
            </div>
          </div>
        )}
      </div>

      <div className="flex items-center justify-between px-3 pt-3">
        <p className="text-[0.72rem] font-medium uppercase tracking-[0.08em] text-muted-foreground">
          근거
        </p>
        <p className="text-[0.72rem] text-muted-foreground">클릭하면 영상 위치로 이동</p>
      </div>

      <ScrollArea className="min-h-0 flex-1 px-3 py-2">
        {evidence.length === 0 ? (
          <p className="p-2 text-xs text-muted-foreground">
            {lastTurn ? "이 답변에는 근거가 없습니다." : "질문하면 근거가 여기 표시됩니다."}
          </p>
        ) : (
          <ul className="space-y-1.5">
            {evidence.map((item) => (
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
                    <span className="inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-full bg-muted px-2 py-0.5 font-mono text-[0.68rem] text-muted-foreground">
                      <Play className="size-3" />
                      {formatTimestamp(item.start_seconds)}–{formatTimestamp(item.end_seconds)}
                    </span>
                    {item.is_primary && (
                      <span className="shrink-0 whitespace-nowrap rounded-full border border-border/70 px-1.5 py-0.5 text-[0.65rem] font-medium text-foreground/70">
                        주요
                      </span>
                    )}
                    <span className="min-w-0 truncate text-muted-foreground">{item.title}</span>
                  </div>
                  {/* 예전엔 근거 인용문이 문장 중간에서 말줄임표로 잘려("짤림") 무슨 내용인지
                      알기 어려웠다. 근거 인용문은 항상 전체를 보여준다. */}
                  <p className="mt-1.5 text-xs leading-relaxed text-foreground/75">
                    {quoteWithHighlight(item)}
                  </p>
                </button>
              </li>
            ))}
          </ul>
        )}
      </ScrollArea>
    </div>
  );
}
