/** VideRAG 로고: 보라→파랑 그라데이션 사각형 + 재생/자막 아이콘. */
export function Logo({ className }: { className?: string }) {
  return (
    <div className={className}>
      <span className="flex items-center gap-2">
        <span className="grid size-8 place-items-center rounded-lg bg-gradient-to-br from-violet-500 to-blue-500 shadow-sm">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M4 6.5A2.5 2.5 0 0 1 6.5 4h7A2.5 2.5 0 0 1 16 6.5v7A2.5 2.5 0 0 1 13.5 16h-7A2.5 2.5 0 0 1 4 13.5z" fill="white" fillOpacity="0.95" />
            <path d="M8 8.2v3.6l3-1.8z" fill="#6d5ef0" />
            <path d="M18 9h2M18 12h2M18 15h2" stroke="white" strokeWidth="1.6" strokeLinecap="round" />
          </svg>
        </span>
        <span className="text-lg font-semibold tracking-tight">VideRAG</span>
      </span>
    </div>
  )
}
