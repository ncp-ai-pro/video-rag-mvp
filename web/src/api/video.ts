import { post, request } from "./client";
import type { JobAccepted, Video } from "./types";

/**
 * GET /videos/{id}는 metadata_embedding(약 23KB)까지 반환하므로 화면에서 쓰지 않는다.
 * 단일 영상 상태는 이 목록 endpoint와 분석 SSE로만 갱신한다.
 */
export async function fetchVideos(channelId: number) {
  return request<Video[]>(`/channels/${channelId}/videos`);
}

// 선택한 영상의 자막 분석 작업 등록
export async function analyzeVideo(videoId: number) {
  return post<JobAccepted>(`/videos/${videoId}/analyze`);
}
