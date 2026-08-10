import { post } from "./client";
import type { RecommendationResponse } from "./types";

// 제목·설명 embedding 유사도 기반 영상 추천 (분석하지 않은 영상도 포함)
export async function fetchRecommendations(query: string, limit = 5) {
  return post<RecommendationResponse>("/recommendations", { query, limit });
}
