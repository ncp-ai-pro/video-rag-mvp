import type { Recommendation } from "./types";

/**
 * 백엔드가 /recommendations에 folder_id·folder_name을 아직 안 내려줘서(요청 예정),
 * 실패 시 헤더 검색 UI를 확인할 수 있도록 목데이터로 대신한다.
 * TODO(backend): 실제 필드가 내려오면 이 폴백을 지운다.
 */
const mockRecommendations: Recommendation[] = [
  {
    video_id: 1,
    folder_id: 1,
    folder_name: "LangGraph RAG",
    title: "LangGraph RAG에서 Conditional Edge를 쓰는 이유",
    description: "",
    url: "https://www.youtube.com/watch?v=eOqXQqg0_Dw",
    thumbnail_url: null,
    duration_seconds: 1122,
    score: 0.91,
    basis: "제목·설명 embedding 유사도",
  },
  {
    video_id: 2,
    folder_id: 1,
    folder_name: "LangGraph RAG",
    title: "CLOVA Studio embedding과 reranking 실습",
    description: "",
    url: "https://www.youtube.com/watch?v=M7lc1UVf-VE",
    thumbnail_url: null,
    duration_seconds: 1930,
    score: 0.76,
    basis: "제목·설명 embedding 유사도",
  },
];

export function mockFetchRecommendations(query: string): Recommendation[] {
  const text = query.trim().toLowerCase();
  if (!text) return [];
  const matched = mockRecommendations.filter(
    (item) => item.title.toLowerCase().includes(text) || item.folder_name.toLowerCase().includes(text),
  );
  // embedding 검색은 글자 그대로 안 겹쳐도 결과가 나올 수 있으니, 목데이터도 최소 하나는 보여준다.
  return matched.length > 0 ? matched : mockRecommendations;
}
