import { useState } from "react";
import {
  ArrowRight,
  ChevronDown,
  Clock,
  FolderKanban,
  Link2,
  ListVideo,
  MessageSquare,
  Rss,
  Search,
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { Footer } from "@/components/Footer";
import { FlowPreview } from "@/components/FlowPreview";
import { Reveal } from "@/components/Reveal";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useFolders } from "@/hooks/queries/folder/use-folders";
import { useStartFolder } from "@/hooks/mutations/folder/use-start-folder";

const FEATURES = [
  "자막 기반 RAG 검색",
  "타임스탬프 근거 제공",
  "영상 내 재생 시점 이동",
];

const PAIN_POINTS = [
  {
    title: "2시간짜리 강의, 처음부터 다시",
    body: "필요한 설명 하나 찾으려고 영상을 앞뒤로 계속 돌려본 적 있으시죠.",
  },
  {
    title: "분명 어디선가 봤는데",
    body: "그 얘기가 몇 분짜리였는지 기억이 안 나서 결국 못 찾고 포기합니다.",
  },
  {
    title: "여러 영상에 흩어진 내용",
    body: "관련 영상은 쌓여 있는데 하나하나 다 챙겨볼 시간은 없습니다.",
  },
];

const INPUT_METHODS = [
  {
    icon: Link2,
    title: "영상 링크 하나",
    body: "URL만 붙여넣으면 바로 자막 분석이 시작돼요.",
  },
  {
    icon: Rss,
    title: "채널 연결",
    body: "채널을 연결해두면 새 영상이 올라올 때마다 자동으로 후보를 찾아드려요.",
  },
  {
    icon: ListVideo,
    title: "재생목록 연결",
    body: "이미 정리해둔 재생목록도 그대로 가져올 수 있어요.",
  },
];

const OUTPUT_FEATURES = [
  {
    icon: MessageSquare,
    title: "AI 채팅",
    body: "영상 내용을 기반으로 궁금한 걸 바로 물어보세요.",
  },
  {
    icon: Clock,
    title: "타임스탬프 근거",
    body: "답변마다 실제로 그 얘기가 나온 구간을 알려줘요.",
  },
  {
    icon: FolderKanban,
    title: "폴더 정리",
    body: "주제별로 폴더를 나눠서 관련 영상만 모아두세요.",
  },
  {
    icon: Rss,
    title: "자동 수집 후보",
    body: "채널을 연결해두면 새 영상 후보를 알아서 추천해요.",
  },
  {
    icon: Search,
    title: "전체 검색",
    body: "이미 분석해둔 영상은 폴더와 상관없이 검색으로 바로 찾아요.",
  },
];

export default function IndexPage() {
  const [url, setUrl] = useState("");
  const navigate = useNavigate();

  const { data: folders = [] } = useFolders();

  // folder-first-api-spec.md의 "첫 시작 화면 API 흐름" 참고. 사이드바의 "폴더 추가"와 같은 훅을 쓴다.
  // 폴더 이름을 먼저 물어보지 않는다 — 영상 제목으로 자동 채워진다(useStartFolder 참고).
  const startMutation = useStartFolder({
    onSettled: (folder) => {
      toast.success(`"${folder.name}" 폴더를 만들고 분석을 시작했습니다.`);
      navigate(`/workspace?folder=${folder.id}`);
    },
    onError: () => toast.error("시작하지 못했습니다."),
  });

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!url.trim()) return;
    startMutation.mutate({ url: url.trim() });
  };

  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      {/* 히어로: 큰 화면에서는 왼쪽 시작 폼 + 오른쪽 실시간 플로우 미리보기 2단, 좁은 화면에선 폼만. */}
      <section className="relative flex min-h-[calc(100dvh-3.5rem)] items-center px-4 py-16">
        <div className="mx-auto grid w-full max-w-5xl items-center gap-12 lg:grid-cols-2">
          <div className="text-center lg:text-left">
            <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">
              YouTube 영상으로 대화하기
            </h1>
            <p className="mt-3 text-muted-foreground">
              영상 링크를 넣으면 폴더가 자동으로 만들어지고, 자막을 분석해 AI에게 질문할 수 있습니다.
            </p>

            <form
              id="start-form"
              onSubmit={submit}
              className="mx-auto mt-8 flex max-w-xl scroll-mt-24 items-center gap-2 rounded-xl border border-border/70 bg-card/60 p-2 shadow-lg lg:mx-0"
            >
              <Input
                type="url"
                required
                value={url}
                placeholder="https://www.youtube.com/watch?v=..."
                aria-label="첫 영상 URL"
                className="border-0 bg-transparent shadow-none focus-visible:ring-0"
                onChange={(event) => setUrl(event.target.value)}
              />
              <Button type="submit" disabled={startMutation.isPending || !url.trim()}>
                {startMutation.isPending ? "시작 중…" : "분석 시작"}
              </Button>
            </form>

            <div className="mt-5 flex flex-wrap justify-center gap-2 lg:justify-start">
              {FEATURES.map((feature) => (
                <span
                  key={feature}
                  className="rounded-full border border-border/60 bg-card/40 px-3 py-1 text-xs text-muted-foreground"
                >
                  {feature}
                </span>
              ))}
            </div>

            {/* 홈은 랜딩 페이지 성격이라 폴더를 직접 고르게 하지 않는다.
                폴더 전환은 작업 환경(Sidebar)의 일이라, 여기선 진입 버튼 하나만 둔다. */}
            {folders.length > 0 && (
              <div className="mt-8">
                <Button variant="outline" onClick={() => navigate("/workspace")}>
                  내 작업 환경 열기 <ArrowRight className="size-4" />
                </Button>
              </div>
            )}
          </div>

          <FlowPreview />
        </div>

        {/* 스크롤 유도 힌트. 랜딩 페이지라는 느낌을 주기 위한 장식이라 스크린리더에는 숨긴다. */}
        <a
          href="#pain-points"
          aria-hidden="true"
          className="absolute inset-x-0 bottom-6 flex animate-bounce justify-center text-muted-foreground transition-colors hover:text-foreground"
        >
          <ChevronDown className="size-5" />
        </a>
      </section>

      {/* 페인포인트 */}
      <section id="pain-points" className="scroll-mt-14 border-t border-border/60 px-4 py-20">
        <div className="mx-auto max-w-4xl text-center">
          <Reveal>
            <h2 className="text-2xl font-bold tracking-tight sm:text-3xl">
              이런 적, 있지 않나요?
            </h2>
          </Reveal>
          <div className="mt-10 grid gap-4 text-left sm:grid-cols-3">
            {PAIN_POINTS.map((point, index) => (
              <Reveal key={point.title} delay={index * 100}>
                <div className="h-full rounded-2xl border border-border/60 bg-card/40 p-5">
                  <p className="font-medium">{point.title}</p>
                  <p className="mt-2 text-sm text-muted-foreground">{point.body}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* 입력 방식 */}
      <section className="border-t border-border/60 px-4 py-20">
        <div className="mx-auto max-w-4xl text-center">
          <Reveal>
            <h2 className="text-2xl font-bold tracking-tight sm:text-3xl">
              영상은 어떻게 넣어도 상관없어요
            </h2>
            <p className="mt-3 text-muted-foreground">
              링크 하나든, 채널이든, 재생목록이든 — 다음은 AI가 알아서 합니다.
            </p>
          </Reveal>
          <div className="mt-10 grid gap-4 text-left sm:grid-cols-3">
            {INPUT_METHODS.map(({ icon: Icon, title, body }, index) => (
              <Reveal key={title} delay={index * 100}>
                <div className="h-full rounded-2xl border border-border/60 bg-card/40 p-5">
                  <span className="flex size-10 items-center justify-center rounded-xl bg-primary/15 text-primary">
                    <Icon className="size-5" />
                  </span>
                  <p className="mt-4 font-medium">{title}</p>
                  <p className="mt-1 text-sm text-muted-foreground">{body}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* 결과 기능 */}
      <section className="border-t border-border/60 px-4 py-20">
        <div className="mx-auto max-w-5xl text-center">
          <Reveal>
            <h2 className="text-2xl font-bold tracking-tight sm:text-3xl">
              영상 하나면, 답변 준비 끝
            </h2>
            <p className="mt-3 text-muted-foreground">
              넣기만 하면 질문할 준비까지 전부 자동으로 만들어져요.
            </p>
          </Reveal>
          <div className="mt-10 grid gap-4 text-left sm:grid-cols-2 lg:grid-cols-5">
            {OUTPUT_FEATURES.map(({ icon: Icon, title, body }, index) => (
              <Reveal key={title} delay={index * 80}>
                <div className="h-full rounded-2xl border border-border/60 bg-card/40 p-5">
                  <div className="flex items-center justify-between">
                    <span className="flex size-10 items-center justify-center rounded-xl bg-primary/15 text-primary">
                      <Icon className="size-5" />
                    </span>
                    <span className="font-mono text-xs text-muted-foreground/60">
                      {String(index + 1).padStart(2, "0")}
                    </span>
                  </div>
                  <p className="mt-4 font-medium">{title}</p>
                  <p className="mt-1 text-sm text-muted-foreground">{body}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* 최종 CTA */}
      <section className="border-t border-border/60 px-4 py-20 text-center">
        <Reveal className="mx-auto max-w-2xl">
          <h2 className="text-2xl font-bold tracking-tight sm:text-3xl">지금 바로 시작하세요</h2>
          <p className="mt-3 text-muted-foreground">
            영상 하나로 폴더를 시작합니다. 이후 작업 환경에서 링크를 더 추가하거나
            채널을 연결해 자동으로 모을 수 있습니다.
          </p>
          <Button asChild className="mt-6">
            <a href="#start-form">지금 시작하기</a>
          </Button>
        </Reveal>
      </section>

      <Footer />
    </div>
  );
}
