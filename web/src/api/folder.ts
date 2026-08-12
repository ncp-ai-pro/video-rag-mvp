import { post, request } from "./client";
import { mockFolder } from "./folder.mock";
import { youtubeIdFromUrl } from "@/lib/format";
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
 * docs/design/folder-first-api-spec.md 기준. 백엔드가 아직 구현 중이라 이 파일의 경로는
 * 스펙 문서를 그대로 따른 가정이며, 실제 배포되면 응답 형태를 다시 맞춰야 할 수 있다.
 * "폴더 안 영상"과 "폴더 밖 채팅" 관련 endpoint는 app/main.py(API 서버) 소관으로 가정했다
 * (지금 /channels, /videos/* 가 API 서버에 있는 것과 같은 분류).
 *
 * 백엔드가 아직 없어서, 실제 호출이 실패하면(404 등) api/folder.mock.ts의 메모리 목데이터로
 * 폴백해서 UI를 눈으로 확인할 수 있게 했다.
 * TODO(backend): /folders가 실제로 배포되면 아래 catch 폴백을 전부 지운다.
 */
function warnMockFallback(context: string) {
  console.warn(`[mock] ${context} 실패해서 목데이터로 대신합니다. 백엔드 배포되면 이 폴백을 지우세요.`);
}

// 폴더 목록 조회 (좌측 사이드바)
export async function fetchFolders() {
  try {
    return await request<Folder[]>("/folders");
  } catch {
    warnMockFallback("GET /folders");
    return mockFolder.fetchFolders();
  }
}

// 폴더 생성. URL 없이 이름만으로 만든다.
export async function createFolder(name: string, description?: string, color?: string) {
  try {
    return await post<FolderCreateResponse>("/folders", { name, description, color });
  } catch {
    warnMockFallback("POST /folders");
    return mockFolder.createFolder(name);
  }
}

// 폴더 이름 등을 바꾼다. 홈 화면에서 임시 이름으로 만든 폴더를 영상 제목으로 바로 바꿀 때 쓴다.
export async function updateFolder(folderId: number, patch: { name?: string }) {
  try {
    return await request<Folder>(`/folders/${folderId}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    });
  } catch {
    warnMockFallback(`PATCH /folders/${folderId}`);
    return mockFolder.updateFolder(folderId, patch);
  }
}

interface RawFolderVideoItem {
  id: number;
  folder_id: number;
  title: string;
  url: string;
  thumbnail_url: string | null;
  duration_seconds: number | null;
  source: FolderVideo["source"];
  source_label: string | null;
  analysis_status: FolderVideo["analysis_status"];
  analysis_stage: FolderVideo["analysis_stage"];
  analysis_message: string | null;
  evidence_count: number;
  added_at: string;
  analyzed_at: string | null;
}

function toFolderVideo(item: RawFolderVideoItem): FolderVideo {
  return {
    ...item,
    platform_video_id: youtubeIdFromUrl(item.url) ?? "",
    description: "",
    uploaded_at: item.added_at,
    analysis_error: null,
    analysis_updated_at: item.analyzed_at,
  };
}

// 폴더 안 영상 목록. 응답에 없는 platform_video_id 등은 여기서 채워서
// Video와 호환되게 만든다(Player·VideoStage를 그대로 재사용하기 위함).
export async function fetchFolderVideos(folderId: number) {
  try {
    const response = await request<{ items: RawFolderVideoItem[]; next_cursor: string | number | null }>(
      `/folders/${folderId}/videos`,
    );
    return response.items.map(toFolderVideo);
  } catch {
    warnMockFallback(`GET /folders/${folderId}/videos`);
    return mockFolder.fetchFolderVideos(folderId);
  }
}

// 폴더에 영상 URL을 직접 추가한다. analyze:true면 서버가 바로 분석 job도 등록한다.
export async function addFolderVideo(folderId: number, url: string, analyze = true) {
  try {
    return await post<{
      video: { id: number; title: string; analysis_status: string };
      folder_video: { folder_id: number; video_id: number; source: string; added_at: string };
      job: JobAccepted | null;
    }>(`/folders/${folderId}/videos`, { url, analyze });
  } catch {
    warnMockFallback(`POST /folders/${folderId}/videos`);
    return mockFolder.addFolderVideo(folderId, url);
  }
}

// 폴더의 수집 후보 목록("분석 전" 영상들).
export async function fetchFolderCandidates(folderId: number) {
  try {
    const response = await request<{ items: FolderCandidate[]; next_cursor: string | number | null }>(
      `/folders/${folderId}/candidates`,
    );
    return response.items;
  } catch {
    warnMockFallback(`GET /folders/${folderId}/candidates`);
    return mockFolder.fetchFolderCandidates(folderId);
  }
}

// 후보를 실제 폴더 영상으로 편입하고 분석 job을 등록한다("분석 후 추가" 버튼).
export async function analyzeCandidate(folderId: number, candidateId: number, analyze = true) {
  try {
    return await post<CandidateAnalyzeResponse>(`/folders/${folderId}/candidates/${candidateId}/analyze`, {
      analyze,
    });
  } catch {
    warnMockFallback(`POST /folders/${folderId}/candidates/${candidateId}/analyze`);
    return mockFolder.analyzeCandidate(folderId, candidateId);
  }
}

// 폴더에 연결된 채널 수집 소스 목록.
export async function fetchChannelSources(folderId: number) {
  try {
    return await request<ChannelSource[]>(`/folders/${folderId}/channel-sources`);
  } catch {
    warnMockFallback(`GET /folders/${folderId}/channel-sources`);
    return mockFolder.fetchChannelSources(folderId);
  }
}

// 폴더에 채널 URL을 수집 소스로 연결한다. auto_scan이면 바로 스캔 job도 등록된다.
export async function addChannelSource(folderId: number, url: string, name?: string) {
  try {
    return await post<ChannelSource & { scan_job: JobAccepted | null }>(`/folders/${folderId}/channel-sources`, {
      url,
      name,
      auto_scan: true,
    });
  } catch {
    warnMockFallback(`POST /folders/${folderId}/channel-sources`);
    return mockFolder.addChannelSource(folderId, url, name);
  }
}

// 이미 연결된 채널 소스를 다시 스캔한다.
export async function scanChannelSource(folderId: number, sourceId: number) {
  try {
    return await post<JobAccepted>(`/folders/${folderId}/channel-sources/${sourceId}/scan`);
  } catch {
    warnMockFallback(`POST /folders/${folderId}/channel-sources/${sourceId}/scan`);
    return mockFolder.scanChannelSource();
  }
}
