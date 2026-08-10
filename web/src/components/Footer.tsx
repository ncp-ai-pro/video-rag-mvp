/**
 * 서비스 고지문. 이전에는 각 패널에 흩어져 있던 "과장하지 않기" 원칙을 여기로 모았다.
 */
export function Footer() {
  return (
    <footer className="border-t border-border/60 px-4 py-4 text-xs text-muted-foreground sm:px-6">
      <div className="mx-auto flex max-w-[1600px] flex-col gap-1.5 sm:flex-row sm:items-center sm:justify-between">
        <span className="font-medium text-foreground/70">VideRAG</span>
        <ul className="flex flex-wrap gap-x-4 gap-y-1">
          <li>추천은 제목·설명 embedding 유사도 기반이며 영상 내용을 검증하지 않습니다.</li>
          <li>답변 근거는 분석된 자막의 실제 재생 시점입니다.</li>
          <li>분석하지 않은 영상은 질문에 답하지 않습니다.</li>
        </ul>
      </div>
    </footer>
  )
}
