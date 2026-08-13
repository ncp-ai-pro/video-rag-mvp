import type { AnalysisStage, AnalysisStatus } from '@/api/types'

// userAgentData는 아직 TS DOM lib에 없다. 모바일 판별에만 쓴다.
declare global {
  interface Navigator {
    userAgentData?: { mobile?: boolean }
  }
}

/** 12.5 → "0:12" */
export function formatTimestamp(seconds: number): string {
  const total = Math.floor(seconds)
  const minutes = Math.floor(total / 60)
  return `${minutes}:${String(total % 60).padStart(2, '0')}`
}

/** 610 → "10분 10초" */
export function formatDuration(seconds: number | null): string | null {
  if (seconds === null) return null
  const minutes = Math.floor(seconds / 60)
  const rest = seconds % 60
  return minutes > 0 ? `${minutes}분 ${rest}초` : `${rest}초`
}

/** yt-dlp가 주는 "20260101" 형식을 화면용으로 바꾼다. */
export function formatUploadDate(value: string | null): string {
  if (!value) return '업로드일 미확인'
  const compact = /^(\d{4})(\d{2})(\d{2})$/.exec(value)
  if (compact) return `${compact[1]}.${compact[2]}.${compact[3]}`
  return value
}

export const STAGE_LABEL: Record<AnalysisStage, string> = {
  metadata_pending: '영상 정보 수집 대기',
  metadata_only: '메타데이터만 수집됨',
  queued: '대기 중',
  downloading_caption: '자막 수집 중',
  transcribing: '음성 인식 중',
  chunking: '구간 분할 중',
  embedding: 'embedding 생성 중',
  completed: '분석 완료',
  failed: '분석 실패',
}

export const STATUS_LABEL: Record<AnalysisStatus, string> = {
  metadata_pending: '정보 수집 중',
  metadata_only: '미분석',
  queued: '대기',
  running: '분석 중',
  succeeded: '분석 완료',
  ready: '분석 완료',
  failed: '실패',
}

/** 진행률 표시용. 실제 백분율이 아니라 stage 순서 기반 근사치다. */
const STAGE_ORDER: AnalysisStage[] = [
  'metadata_pending',
  'queued',
  'downloading_caption',
  'transcribing',
  'chunking',
  'embedding',
  'completed',
]

export function stageProgress(stage: AnalysisStage): number {
  if (stage === 'failed') return 100
  const index = STAGE_ORDER.indexOf(stage)
  if (index < 0) return 0
  return Math.round(((index + 1) / STAGE_ORDER.length) * 100)
}

/**
 * 진행 화면의 스텝 표시용. 백엔드 stage를 목업의 4단계로 묶는다.
 * transcribing(음성 인식)은 자막이 없을 때만 거치므로 '자막 추출'에 함께 묶는다.
 */
export interface ProgressStep {
  key: string
  label: string
  stages: AnalysisStage[]
}

export const PROGRESS_STEPS: ProgressStep[] = [
  { key: 'caption', label: '자막 추출', stages: ['downloading_caption', 'transcribing'] },
  { key: 'chunking', label: '구간 분할', stages: ['chunking'] },
  { key: 'embedding', label: '임베딩 인덱싱', stages: ['embedding'] },
  { key: 'completed', label: '분석 완료', stages: ['completed'] },
]

export type StepState = 'done' | 'active' | 'pending'

/** 현재 stage 기준으로 각 스텝이 완료/진행/대기 중 어디인지 계산한다. */
export function stepState(step: ProgressStep, current: AnalysisStage): StepState {
  const order = PROGRESS_STEPS.findIndex((s) => s.key === step.key)
  const currentOrder = PROGRESS_STEPS.findIndex((s) => s.stages.includes(current))
  // queued 등 스텝 이전 단계면 전부 대기.
  if (currentOrder < 0) return 'pending'
  if (order < currentOrder) return 'done'
  if (order === currentOrder) return current === 'completed' ? 'done' : 'active'
  return 'pending'
}

/** 근거 url(`...watch?v=ID&t=12s`)에서 YouTube 영상 ID만 뽑는다. */
export function youtubeIdFromUrl(rawUrl: string): string | null {
  try {
    const url = new URL(rawUrl)
    if (url.hostname === 'youtu.be') return url.pathname.slice(1) || null
    return url.searchParams.get('v')
  } catch {
    return null
  }
}

/**
 * 모바일에서는 youtu.be 링크가 앱으로 더 잘 열린다.
 * 백엔드가 준 ?t=12s 타임스탬프는 그대로 옮긴다.
 */
export function playbackUrl(rawUrl: string): string {
  try {
    const source = new URL(rawUrl)
    if (!/(^|\.)youtube\.com$/.test(source.hostname)) return rawUrl
    const videoId = source.searchParams.get('v')
    if (!videoId) return rawUrl
    const timestamp = source.searchParams.get('t')

    const isMobile =
      navigator.userAgentData?.mobile === true ||
      /Android|iPhone|iPad|iPod|IEMobile|Opera Mini/i.test(navigator.userAgent)

    const target = isMobile
      ? new URL(`https://youtu.be/${encodeURIComponent(videoId)}`)
      : new URL('https://www.youtube.com/watch')
    if (!isMobile) target.searchParams.set('v', videoId)
    if (timestamp) target.searchParams.set('t', timestamp)
    return target.toString()
  } catch {
    return rawUrl
  }
}
