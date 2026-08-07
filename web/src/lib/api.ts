import { API_BASE } from './config'
import type {
  Channel,
  JobAccepted,
  RecommendationResponse,
  Video,
  Workspace,
} from './types'

export class ApiError extends Error {
  // erasableSyntaxOnly가 켜져 있어 constructor 파라미터 프로퍼티는 쓸 수 없다.
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

/** FastAPI는 오류를 {detail: string} 또는 {detail: ValidationError[]}로 준다. */
async function readErrorMessage(response: Response): Promise<string> {
  const body = await response.json().catch(() => null)
  const detail = body?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail.length > 0) {
    return detail.map((item) => item.msg).join(', ')
  }
  return `요청에 실패했습니다. (HTTP ${response.status})`
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    credentials: 'same-origin',
    ...init,
    headers: { 'Content-Type': 'application/json', ...init.headers },
  })
  if (!response.ok) {
    throw new ApiError(await readErrorMessage(response), response.status)
  }
  // 204 No Content는 본문이 없다.
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T)
}

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, {
    method: 'POST',
    body: body === undefined ? undefined : JSON.stringify(body),
  })

export const api = {
  health: () => request<{ status: string; queue: string; mode: string }>('/health'),

  me: () => request<Workspace>('/auth/me'),
  connectWorkspace: (workspaceCode: string) =>
    post<Workspace>('/auth/workspace', { workspace_code: workspaceCode }),
  newWorkspace: () => post<Workspace>('/auth/new-workspace'),

  listChannels: () => request<Channel[]>('/channels'),
  createChannel: (url: string, name?: string) =>
    post<Channel>('/channels', { url, name: name || null }),
  scanChannel: (channelId: number) =>
    post<JobAccepted>(`/channels/${channelId}/scan`),

  listVideos: (channelId: number) =>
    request<Video[]>(`/channels/${channelId}/videos`),
  analyzeVideo: (videoId: number) =>
    post<JobAccepted>(`/videos/${videoId}/analyze`),

  recommend: (query: string, limit = 5) =>
    post<RecommendationResponse>('/recommendations', { query, limit }),
}

/**
 * GET /videos/{id}는 metadata_embedding(약 23KB)까지 반환하므로 화면에서 쓰지 않는다.
 * 단일 영상 상태는 목록 응답과 SSE로 갱신한다.
 */
