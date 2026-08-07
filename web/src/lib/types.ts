/**
 * 백엔드에 response_model이 없어 OpenAPI에 응답 스키마가 없다.
 * 아래 타입은 실행 중인 서버의 실제 응답을 확인해 작성했다.
 */

export interface Workspace {
  id: number
  workspace_code: string
}

export interface Channel {
  id: number
  user_id: number
  url: string
  name: string | null
  created_at: string
  last_scanned_at: string | null
}

/** jobs.status와 동일한 어휘 */
export type AnalysisStatus =
  | 'metadata_only'
  | 'queued'
  | 'running'
  | 'succeeded'
  | 'failed'
  /** 구버전 데이터에 남아 있는 값. succeeded와 같게 취급한다. */
  | 'ready'

/** services.ANALYSIS_MESSAGES의 key와 동일. 새 stage 추가 시 백엔드와 함께 갱신할 것. */
export type AnalysisStage =
  | 'metadata_only'
  | 'queued'
  | 'downloading_caption'
  | 'transcribing'
  | 'chunking'
  | 'embedding'
  | 'completed'
  | 'failed'

/** GET /channels/{id}/videos 의 항목. 목록 endpoint는 embedding을 제외한 컬럼만 반환한다. */
export interface Video {
  id: number
  platform_video_id: string
  title: string
  description: string
  url: string
  thumbnail_url: string | null
  duration_seconds: number | null
  uploaded_at: string | null
  analysis_status: AnalysisStatus
  analysis_stage: AnalysisStage
  analysis_message: string | null
  analysis_error: string | null
  analysis_updated_at: string | null
}

export interface JobAccepted {
  job_id: number
  status: 'queued'
}

/** GET /videos/{id}/events 가 보내는 analysis_status 이벤트 */
export interface AnalysisEvent {
  video_id: number
  job_id: number
  status: AnalysisStatus
  progress: {
    stage: AnalysisStage
    message: string
  }
  error: string | null
  updated_at: string | null
}

export interface Recommendation {
  video_id: number
  title: string
  description: string
  url: string
  thumbnail_url: string | null
  duration_seconds: number | null
  uploaded_at: string | null
  score: number
  basis: string
}

export interface RecommendationResponse {
  query: string
  items: Recommendation[]
  notice: string
}

/** url에는 이미 ?t={start}s 가 붙어 있다. */
export interface Evidence {
  video_id: number
  title: string
  start_seconds: number
  end_seconds: number
  quote: string
  url: string
  score: number
}

export interface ChatResponse {
  answer: string
  evidence: Evidence[]
}

/** GET /chat/history 의 항목. assistant 메시지는 저장된 근거 구간을 함께 돌려줄 수 있다. */
export interface ChatMessage {
  id: number
  role: 'user' | 'assistant'
  content: string
  evidence?: Evidence[]
  created_at: string | null
}

export interface ChatHistoryPage {
  items: ChatMessage[]
  messages?: ChatMessage[]
  has_more: boolean
  next_cursor: number | null
}

export const isAnalyzed = (status: AnalysisStatus) =>
  status === 'succeeded' || status === 'ready'

export const isAnalysisActive = (status: AnalysisStatus) =>
  status === 'queued' || status === 'running'
