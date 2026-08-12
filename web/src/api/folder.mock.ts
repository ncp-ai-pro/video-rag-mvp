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
 * 백엔드 /folders API가 아직 없어서(docs/design/folder-first-api-spec.md 구현 전) UI를
 * 눈으로 확인할 수 있도록 메모리에 목데이터를 둔다. api/folder.ts·api/chat.ts가 실제 호출
 * 실패 시 여기로 폴백한다.
 * TODO(backend): /folders가 실제로 배포되면 이 파일과 각 함수의 폴백 코드를 지운다.
 */

let nextFolderId = 2;
let nextVideoId = 1001;

const now = () => new Date().toISOString();

const folders: Folder[] = [
  {
    id: 1,
    name: "LangGraph RAG",
    description: "조건부 엣지와 RAG 실습 영상 모음",
    color: "amber",
    video_count: 2,
    ready_count: 1,
    running_count: 1,
    candidate_count: 1,
    updated_at: now(),
  },
];

const videosByFolder: Record<number, FolderVideo[]> = {
  1: [
    {
      id: 1,
      folder_id: 1,
      platform_video_id: "eOqXQqg0_Dw",
      title: "LangGraph RAG에서 Conditional Edge를 쓰는 이유",
      description: "",
      url: "https://www.youtube.com/watch?v=eOqXQqg0_Dw",
      thumbnail_url: null,
      duration_seconds: 1122,
      uploaded_at: null,
      analysis_status: "ready",
      analysis_stage: "completed",
      analysis_message: "분석이 완료되었습니다. 이제 질문할 수 있습니다.",
      analysis_error: null,
      analysis_updated_at: now(),
      source: "direct",
      source_label: null,
      evidence_count: 12,
      added_at: now(),
      analyzed_at: now(),
    },
    {
      id: 2,
      folder_id: 1,
      platform_video_id: "M7lc1UVf-VE",
      title: "CLOVA Studio embedding과 reranking 실습",
      description: "",
      url: "https://www.youtube.com/watch?v=M7lc1UVf-VE",
      thumbnail_url: null,
      duration_seconds: 1930,
      uploaded_at: null,
      analysis_status: "running",
      analysis_stage: "embedding",
      analysis_message: "자막 구간의 embedding을 생성하고 있습니다.",
      analysis_error: null,
      analysis_updated_at: now(),
      source: "channel_scan",
      source_label: "NAVER Cloud AI",
      evidence_count: 0,
      added_at: now(),
      analyzed_at: null,
    },
  ],
};

const candidatesByFolder: Record<number, FolderCandidate[]> = {
  1: [
    {
      id: 91,
      folder_id: 1,
      channel_source_id: 7,
      video_id: null,
      title: "LangGraph Agent Supervisor 실습",
      description: "",
      url: "https://www.youtube.com/watch?v=jNQXAC9IVRw",
      thumbnail_url: null,
      duration_seconds: 980,
      source_label: "NAVER Cloud AI",
      score: 0.84,
      basis: "폴더 주제와 제목/설명 embedding 유사도",
      status: "new",
    },
  ],
};

const channelSourcesByFolder: Record<number, ChannelSource[]> = {
  1: [
    {
      id: 7,
      folder_id: 1,
      url: "https://www.youtube.com/@navercloud",
      name: "NAVER Cloud AI",
      last_scanned_at: now(),
      candidate_count: 1,
    },
  ],
};

export const mockFolder = {
  fetchFolders(): Folder[] {
    return folders;
  },

  createFolder(name: string): FolderCreateResponse {
    const id = nextFolderId++;
    const createdAt = now();
    folders.push({
      id,
      name,
      description: null,
      color: null,
      video_count: 0,
      ready_count: 0,
      running_count: 0,
      candidate_count: 0,
      updated_at: createdAt,
    });
    videosByFolder[id] = [];
    candidatesByFolder[id] = [];
    channelSourcesByFolder[id] = [];
    return { id, name, description: null, color: null, created_at: createdAt };
  },

  updateFolder(folderId: number, patch: { name?: string }): Folder {
    const folder = folders.find((item) => item.id === folderId);
    if (!folder) throw new Error("폴더를 찾을 수 없습니다.");
    if (patch.name) folder.name = patch.name;
    folder.updated_at = now();
    return folder;
  },

  fetchFolderVideos(folderId: number): FolderVideo[] {
    return videosByFolder[folderId] ?? [];
  },

  addFolderVideo(folderId: number, url: string) {
    const id = nextVideoId++;
    const addedAt = now();
    const video: FolderVideo = {
      id,
      folder_id: folderId,
      platform_video_id: youtubeIdFromUrl(url) ?? String(id),
      title: `새 영상 ${id}`,
      description: "",
      url,
      thumbnail_url: null,
      duration_seconds: null,
      uploaded_at: null,
      analysis_status: "queued",
      analysis_stage: "queued",
      analysis_message: "분석 작업을 기다리고 있습니다.",
      analysis_error: null,
      analysis_updated_at: null,
      source: "direct",
      source_label: null,
      evidence_count: 0,
      added_at: addedAt,
      analyzed_at: null,
    };
    (videosByFolder[folderId] ??= []).push(video);
    const folder = folders.find((item) => item.id === folderId);
    if (folder) folder.video_count += 1;
    return {
      video: { id: video.id, title: video.title, analysis_status: video.analysis_status },
      folder_video: { folder_id: folderId, video_id: id, source: "direct", added_at: addedAt },
      job: { job_id: id, status: "queued" as const },
    };
  },

  fetchFolderCandidates(folderId: number): FolderCandidate[] {
    return candidatesByFolder[folderId] ?? [];
  },

  analyzeCandidate(folderId: number, candidateId: number): CandidateAnalyzeResponse {
    const list = candidatesByFolder[folderId] ?? [];
    const candidate = list.find((item) => item.id === candidateId);
    if (!candidate) throw new Error("후보를 찾을 수 없습니다.");

    const videoId = nextVideoId++;
    const addedAt = now();
    const video: FolderVideo = {
      id: videoId,
      folder_id: folderId,
      platform_video_id: youtubeIdFromUrl(candidate.url) ?? String(videoId),
      title: candidate.title,
      description: candidate.description,
      url: candidate.url,
      thumbnail_url: candidate.thumbnail_url,
      duration_seconds: candidate.duration_seconds,
      uploaded_at: null,
      analysis_status: "queued",
      analysis_stage: "queued",
      analysis_message: "분석 작업을 기다리고 있습니다.",
      analysis_error: null,
      analysis_updated_at: null,
      source: "candidate",
      source_label: candidate.source_label,
      evidence_count: 0,
      added_at: addedAt,
      analyzed_at: null,
    };
    (videosByFolder[folderId] ??= []).push(video);
    candidatesByFolder[folderId] = list.filter((item) => item.id !== candidateId);

    return {
      candidate: { id: candidateId, status: "added" },
      video: { id: videoId, title: video.title, analysis_status: "queued" },
      folder_video: { folder_id: folderId, video_id: videoId, source: "candidate" },
      job: { job_id: videoId, status: "queued" },
    };
  },

  fetchChannelSources(folderId: number): ChannelSource[] {
    return channelSourcesByFolder[folderId] ?? [];
  },

  addChannelSource(folderId: number, url: string, name?: string) {
    const id = nextVideoId++;
    const source: ChannelSource = {
      id,
      folder_id: folderId,
      url,
      name: name ?? null,
      last_scanned_at: null,
      candidate_count: 0,
    };
    (channelSourcesByFolder[folderId] ??= []).push(source);
    return { ...source, scan_job: { job_id: id, status: "queued" as const } };
  },

  scanChannelSource(): JobAccepted {
    return { job_id: nextVideoId++, status: "queued" };
  },
};
