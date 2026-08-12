import { useMutation } from "@tanstack/react-query";

import { fetchRecommendations } from "@/api/recommendation";
import type { UseMutationCallback } from "@/hooks/types";

interface Args {
  query: string;
  limit?: number;
}

/** 헤더 전역 검색: 워크스페이스 전체에서 제목·설명 embedding 유사도로 영상을 찾는다. */
export function useRecommend(callbacks?: UseMutationCallback) {
  return useMutation({
    mutationFn: ({ query, limit }: Args) => fetchRecommendations(query, limit),
    onError: (error) => callbacks?.onError?.(error),
  });
}
