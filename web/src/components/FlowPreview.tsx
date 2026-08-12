import { CheckCircle2, FolderPlus, Link2, MessageSquare } from "lucide-react";

/**
 * 히어로 옆에서 계속 반복 재생되는 "실제 동작 미리보기" 카드 스택.
 * 참고한 초기 mockup(video-rag-chat-first-mockup.html)의 flow-card 루프 애니메이션과 같은 방식 —
 * CSS @keyframes(index.css의 flow-card/flow-progress)로 카드가 순서대로 나타났다 사라진다.
 */
const STEPS = [
  {
    icon: Link2,
    title: "1. 영상 링크 입력",
    body: "youtube.com/watch?v=...",
  },
  {
    icon: FolderPlus,
    title: "2. 폴더 자동 생성",
    body: "영상 제목으로 폴더 이름이 자동으로 채워져요",
  },
  {
    icon: CheckCircle2,
    title: "3. 자막 분석 진행",
    body: "자막 → 구간 나누기 → embedding까지 자동으로",
    progress: true,
  },
  {
    icon: MessageSquare,
    title: "4. 질문하고 답변받기",
    body: "타임스탬프 근거와 함께 바로 답이 와요",
  },
] as const;

const DURATION = 9;
const STEP_DELAY = DURATION / STEPS.length;

export function FlowPreview() {
  return (
    <div className="hidden rounded-2xl border border-border/60 bg-card/40 p-4 lg:block">
      <p className="mb-3 text-xs font-medium text-muted-foreground">실제 동작 미리보기</p>
      <div className="relative h-[320px]">
        {STEPS.map((step, index) => (
          <div
            key={step.title}
            className="absolute inset-x-0 flex flex-col gap-2 rounded-xl border border-border/60 bg-background p-4 opacity-0 shadow-lg"
            style={{
              top: `${index * 78}px`,
              animation: `flow-card ${DURATION}s ease-in-out infinite`,
              animationDelay: `${index * STEP_DELAY}s`,
            }}
          >
            <div className="flex items-center gap-2">
              <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary/15 text-primary">
                <step.icon className="size-4" />
              </span>
              <p className="text-sm font-medium">{step.title}</p>
            </div>
            <p className="pl-10 text-xs text-muted-foreground">{step.body}</p>
            {"progress" in step && step.progress && (
              <div className="ml-10 h-1.5 overflow-hidden rounded-full bg-muted">
                <div
                  className="h-full w-0 rounded-full bg-primary"
                  style={{
                    animation: `flow-progress ${DURATION}s ease-in-out infinite`,
                    animationDelay: `${index * STEP_DELAY}s`,
                  }}
                />
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
