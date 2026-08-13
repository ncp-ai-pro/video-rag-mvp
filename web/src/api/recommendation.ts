import { post } from "./client";
import { mockFetchRecommendations } from "./recommendation.mock";
import type { RecommendationResponse } from "./types";

// 제목·설명 embedding 유사도 기반 영상 추천 (워크스페이스 전체, 분석하지 않은 영상도 포함)
export async function fetchRecommendations(query: string, limit = 5) {
  try {
    return await post<RecommendationResponse>("/recommendations", { query, limit });
  } catch {
    console.warn("[mock] POST /recommendations 실패해서 목데이터로 대신합니다.");
    return {
      query,
      items: mockFetchRecommendations(query),
      notice: "추천은 제목과 영상 설명의 embedding 유사도 기반이며 영상 내용을 검증하지 않습니다.",
    } satisfies RecommendationResponse;
  }
}
