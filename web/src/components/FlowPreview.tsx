import { useEffect, useState } from "react";
import { Check, CheckCircle2, FolderPlus, Link2, MessageSquare } from "lucide-react";

/**
 * 히어로 옆(모바일에서는 아래)에서 계속 반복 재생되는 "실제 동작 미리보기".
 * 세로 타임라인 형태로, 한 번에 한 단계만 활성화되어 진행되는 방식이다.
 * 모바일에서도 제품이 실제로 어떻게 동작하는지 보여주는 유일한 시각 자료라 breakpoint로 숨기지 않는다.
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

const STEP_DURATION = 2600;

export function FlowPreview() {
  // tick은 매 단계마다 1씩 증가하는 누적 카운터. active 단계는 tick % 길이로 구하고,
  // 진행바는 tick을 key로 써서 같은 단계로 돌아올 때마다 애니메이션이 처음부터 다시 시작되게 한다.
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => setTick((prev) => prev + 1), STEP_DURATION);
    return () => clearInterval(timer);
  }, []);

  const active = tick % STEPS.length;

  return (
    <div className="rounded-2xl border border-border/60 bg-card/40 p-4">
      <p className="mb-4 text-xs font-medium text-muted-foreground">실제 동작 미리보기</p>
      <ol className="flex flex-col">
        {STEPS.map((step, index) => {
          const status = index < active ? "done" : index === active ? "active" : "upcoming";
          const isLast = index === STEPS.length - 1;

          return (
            <li key={step.title} className="relative flex gap-3">
              {!isLast && (
                <span
                  className={`absolute left-[15px] top-8 h-[calc(100%-1rem)] w-px transition-colors duration-500 ${
                    status === "done" ? "bg-primary/50" : "bg-border"
                  }`}
                />
              )}
              <span
                className={`relative z-10 flex size-8 shrink-0 items-center justify-center rounded-full border transition-colors duration-500 ${
                  status === "done"
                    ? "border-primary bg-primary text-primary-foreground"
                    : status === "active"
                      ? "border-primary bg-primary/15 text-primary"
                      : "border-border bg-background text-muted-foreground/40"
                }`}
              >
                {status === "done" ? <Check className="size-4" /> : <step.icon className="size-4" />}
              </span>
              <div
                className={`flex-1 pb-6 transition-opacity duration-500 ${
                  status === "upcoming" ? "opacity-40" : "opacity-100"
                }`}
              >
                <p className="text-sm font-medium">{step.title}</p>
                {status !== "upcoming" && (
                  <p className="mt-1 text-xs text-muted-foreground">{step.body}</p>
                )}
                {status === "active" && "progress" in step && step.progress && (
                  <div className="mt-2 h-1.5 w-full max-w-40 overflow-hidden rounded-full bg-muted">
                    <div
                      key={tick}
                      className="h-full rounded-full bg-primary"
                      style={{ animation: `fill-progress ${STEP_DURATION}ms linear forwards` }}
                    />
                  </div>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
