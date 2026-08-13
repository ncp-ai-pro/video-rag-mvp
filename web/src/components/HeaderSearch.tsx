import { useState } from "react";
import { Search } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { Input } from "@/components/ui/input";
import { Popover, PopoverAnchor, PopoverContent } from "@/components/ui/popover";
import { useRecommend } from "@/hooks/mutations/recommendation/use-recommend";
import type { Recommendation } from "@/api/types";

/**
 * 헤더 전역 검색: 폴더와 상관없이 워크스페이스 전체에서 이미 분석된 영상을
 * 제목·설명 embedding 유사도로 찾는다. 결과를 고르면 그 영상이 있는 폴더로 이동한다.
 * (채널 연결=새 영상 발견과는 다른 기능이라 폴더 다이얼로그가 아니라 여기 상단에 둔다.)
 */
export function HeaderSearch() {
  const navigate = useNavigate();
  const recommendMutation = useRecommend();

  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Recommendation[] | null>(null);
  const [open, setOpen] = useState(false);

  const search = (event: React.FormEvent) => {
    event.preventDefault();
    if (!query.trim()) return;
    recommendMutation.mutate(
      { query: query.trim() },
      {
        onSuccess: (result) => {
          setResults(result.items);
          setOpen(true);
        },
      },
    );
  };

  const openResult = (item: Recommendation) => {
    setOpen(false);
    // 지금 /recommendations는 실제로 살아있는(구) endpoint라 folder_id를 아직 안 준다.
    // 폴더를 모르면 이동할 곳이 없으니 영상만 새 탭으로 연다.
    if (item.folder_id) navigate(`/workspace?folder=${item.folder_id}`);
    else window.open(item.url, "_blank", "noreferrer");
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverAnchor asChild>
        <form onSubmit={search} className="relative hidden w-full max-w-xs sm:block">
          <Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            placeholder="분석된 영상 검색 (모든 폴더)"
            aria-label="전체 영상 검색"
            className="h-9 pl-8"
            onChange={(event) => setQuery(event.target.value)}
          />
        </form>
      </PopoverAnchor>
      <PopoverContent align="start" className="w-80 p-0">
        <div className="flex items-center justify-between px-3 py-2 text-xs text-muted-foreground">
          <span>제목·설명 유사도 · {results?.length ?? 0}개</span>
          <button type="button" className="hover:text-foreground" onClick={() => setOpen(false)}>
            닫기
          </button>
        </div>
        {recommendMutation.isPending ? (
          <p className="px-3 pb-3 text-xs text-muted-foreground">검색 중…</p>
        ) : !results || results.length === 0 ? (
          <p className="px-3 pb-3 text-xs text-muted-foreground">결과가 없습니다.</p>
        ) : (
          <ul className="max-h-72 overflow-y-auto border-t border-border/60">
            {results.map((item) => (
              <li key={item.video_id}>
                <button
                  type="button"
                  onClick={() => openResult(item)}
                  className="w-full border-b border-border/40 px-3 py-2 text-left transition-colors last:border-0 hover:bg-accent"
                >
                  <p className="line-clamp-1 text-sm">{item.title}</p>
                  <div className="mt-0.5 flex items-center justify-between gap-2">
                    <span className="truncate text-[11px] text-muted-foreground">{item.folder_name}</span>
                    <span className="shrink-0 font-mono text-[11px] text-muted-foreground">
                      {item.score.toFixed(2)}
                    </span>
                  </div>
                </button>
              </li>
            ))}
          </ul>
        )}
      </PopoverContent>
    </Popover>
  );
}
