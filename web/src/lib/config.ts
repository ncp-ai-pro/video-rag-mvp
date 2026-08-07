/**
 * API·Chat이 별도 서버로 배포되므로 base URL을 한 곳에서 결정한다.
 *
 * - dev: vite proxy가 /api → :8000, /chat → :8001 로 넘긴다(같은 오리진이라 쿠키가 그대로 실린다).
 * - prod(Nginx): /api/* prefix를 떼어 API WAS로, /chat은 경로 유지한 채 Chat WAS로 보낸다.
 *   → 두 환경 모두 기본값 그대로 동작한다. docs/infra.md 참고.
 * - Chat이 정말 다른 도메인일 때만 백엔드가 /runtime-config.js로 주입하는
 *   window.VIDEO_RAG_CHAT_ORIGIN이 우선한다.
 */

declare global {
  interface Window {
    VIDEO_RAG_CHAT_ORIGIN?: string
  }
}

const trimEnd = (value: string) => value.replace(/\/+$/, '')

export const API_BASE = trimEnd(import.meta.env.VITE_API_BASE ?? '/api')

export const CHAT_BASE = trimEnd(
  window.VIDEO_RAG_CHAT_ORIGIN || (import.meta.env.VITE_CHAT_BASE ?? ''),
)

/** Chat이 다른 오리진이면 쿠키를 명시적으로 실어야 작업공간이 유지된다. */
export const CHAT_CREDENTIALS: RequestCredentials = CHAT_BASE.startsWith('http')
  ? 'include'
  : 'same-origin'
