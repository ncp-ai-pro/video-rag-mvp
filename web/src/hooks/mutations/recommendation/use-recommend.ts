import { useMutation } from "@tanstack/react-query";

import { fetchRecommendations } from "@/api/recommendation";
import type { UseMutationCallback } from "@/hooks/types";

/** 검색어를 누를 때만 트리거되는 동작이라 query가 아니라 mutation으로 감싼다. */
export function useRecommend(callbacks?: UseMutationCallback) {
  return useMutation({
    mutationFn: ({ query, limit }: { query: string; limit?: number }) =>
      fetchRecommendations(query, limit),
    onError: (error) => callbacks?.onError?.(error),
  });
}
