import { post, request } from "./client";
import type { Channel, JobAccepted } from "./types";

// 채널 목록 조회
export async function fetchChannels() {
  return request<Channel[]>("/channels");
}

// 채널 등록 (URL 필수, 이름은 선택)
export async function createChannel(url: string, name?: string) {
  return post<Channel>("/channels", { url, name: name || null });
}

// 채널의 새 영상 탐색 작업 등록 (메타데이터만 수집, 영상·음성은 내려받지 않음)
export async function scanChannel(channelId: number) {
  return post<JobAccepted>(`/channels/${channelId}/scan`);
}
