import { post, request } from "./client";
import type {
  CandidateAnalyzeResponse,
  ChannelSource,
  Folder,
  FolderCandidate,
  FolderCreateResponse,
  FolderVideo,
  JobAccepted,
} from "./types";

/**
 * docs/design/folder-first-api-spec.md 기준, app/routers/folders.py에 실제 배포됨(API 서버 8000 소관).
 * fetchFolders·createFolder·updateFolder·fetchFolderVideos·addFolderVideo는 curl로 응답 구조를
 * 확인 완료. fetchFolderCandidates·fetchChannelSources는 래핑 구조만 확인했고(현재 빈 배열),
 * 실데이터가 있는 케이스는 아직 검증하지 않았다.
 */

// 폴더 목록 조회 (좌측 사이드바)
export async function fetchFolders() {
  return request<Folder[]>("/folders");
}

// 폴더 생성. URL 없이 이름만으로 만든다.
export async function createFolder(name: string, description?: string, color?: string) {
  return post<FolderCreateResponse>("/folders", { name, description, color });
}

// 폴더 이름 등을 바꾼다. 홈 화면에서 임시 이름으로 만든 폴더를 영상 제목으로 바로 바꿀 때 쓴다.
export async function updateFolder(folderId: number, patch: { name?: string }) {
  return request<Folder>(`/folders/${folderId}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

// 폴더 안 영상 목록.
export async function fetchFolderVideos(folderId: number) {
  const response = await request<{ items: FolderVideo[]; next_cursor: string | number | null }>(
    `/folders/${folderId}/videos`,
  );
  return response.items;
}

// 폴더에 영상 URL을 직접 추가한다. analyze:true면 서버가 바로 분석 job도 등록한다.
export async function addFolderVideo(folderId: number, url: string, analyze = true) {
  return post<{
    video: { id: number; title: string; analysis_status: string };
    folder_video: { folder_id: number; video_id: number; source: string; added_at: string };
    job: JobAccepted | null;
  }>(`/folders/${folderId}/videos`, { url, analyze });
}

// 폴더의 수집 후보 목록("분석 전" 영상들).
export async function fetchFolderCandidates(folderId: number) {
  const response = await request<{ items: FolderCandidate[]; next_cursor: string | number | null }>(
    `/folders/${folderId}/candidates`,
  );
  return response.items;
}

// 후보를 실제 폴더 영상으로 편입하고 분석 job을 등록한다("분석 후 추가" 버튼).
export async function analyzeCandidate(folderId: number, candidateId: number, analyze = true) {
  return post<CandidateAnalyzeResponse>(`/folders/${folderId}/candidates/${candidateId}/analyze`, {
    analyze,
  });
}

// 폴더에 연결된 채널 수집 소스 목록.
export async function fetchChannelSources(folderId: number) {
  return request<ChannelSource[]>(`/folders/${folderId}/channel-sources`);
}

// 폴더에 채널 URL을 수집 소스로 연결한다. auto_scan이면 바로 스캔 job도 등록된다.
export async function addChannelSource(folderId: number, url: string, name?: string) {
  return post<ChannelSource & { scan_job: JobAccepted | null }>(`/folders/${folderId}/channel-sources`, {
    url,
    name,
    auto_scan: true,
  });
}

// 이미 연결된 채널 소스를 다시 스캔한다.
export async function scanChannelSource(folderId: number, sourceId: number) {
  return post<JobAccepted>(`/folders/${folderId}/channel-sources/${sourceId}/scan`);
}

// 폴더를 삭제한다. 폴더 안 영상·후보·채널 소스도 함께 삭제된다(되돌릴 수 없음).
export async function deleteFolder(folderId: number) {
  return request<void>(`/folders/${folderId}`, { method: "DELETE" });
}
