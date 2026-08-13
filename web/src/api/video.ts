import { post } from "./client";
import type { JobAccepted } from "./types";

// 선택한 영상의 자막 분석 작업 등록
export async function analyzeVideo(videoId: number) {
  return post<JobAccepted>(`/videos/${videoId}/analyze`);
}
