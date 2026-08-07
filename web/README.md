# Video RAG 프론트엔드

React + Vite + TypeScript + Tailwind v4 + shadcn/ui.

## 실행

백엔드 3개를 먼저 띄운다(프로젝트 루트에서).

```bash
.venv/bin/uvicorn app.main:app --reload --port 8000        # API
.venv/bin/uvicorn app.chat_main:app --reload --port 8001   # Chat Server
.venv/bin/python -m app.worker                             # Worker
```

그다음 이 디렉토리에서:

```bash
npm install
npm run dev      # http://localhost:5173
# npm run build    # tsc -b && vite build → dist/
# npm run lint
```

포트가 다르면 환경변수로 바꾼다.

```bash
VITE_DEV_API_TARGET=http://127.0.0.1:9000 npm run dev
VITE_DEV_CHAT_TARGET=http://127.0.0.1:9001 npm run dev
```

## base URL 규칙

API와 Chat이 **서로 다른 서버**라 base URL을 `src/lib/config.ts`에서 한 번만 정한다.

| 환경         | API                                       | Chat                               |
| ------------ | ----------------------------------------- | ---------------------------------- |
| dev          | `/api` → vite proxy가 prefix를 떼고 :8000 | `/chat` → vite proxy가 :8001       |
| prod (Nginx) | `/api/*` → prefix 제거 후 API WAS         | `/chat`, `/chat/stream` → Chat WAS |

두 환경 모두 기본값 그대로 동작한다. `docs/infra.md`의 Nginx 규칙에 맞춘 값이다.

Chat을 정말 다른 도메인에 두는 경우에만 백엔드가 `/runtime-config.js`로 주입하는
`window.VIDEO_RAG_CHAT_ORIGIN`이 우선한다. 이때는 쿠키를 위해 `credentials: 'include'`로
전환되므로 백엔드의 `CORS_ALLOW_ORIGINS`와 `SESSION_COOKIE_DOMAIN`도 함께 설정해야 한다.

빌드 타임 고정값이 필요하면 `VITE_API_BASE`, `VITE_CHAT_BASE`로 덮어쓴다.

## SSE 두 종류

백엔드에 성격이 다른 스트림이 둘 있고, 각각 다른 방식으로 읽는다.

**분석 진행** — `GET /videos/{id}/events` · `src/hooks/useAnalysisEvents.ts`

GET이라 `EventSource`를 그대로 쓴다. 서버가 `retry: 3000`을 보내므로 끊겨도 브라우저가
재연결한다. `succeeded`/`failed`가 오면 서버가 stream을 닫으므로 훅에서도 즉시 close한다.
분석이 진행 중인 영상에만 연결한다.

**Chat 응답** — `POST /chat/stream` · `src/lib/chat.ts`

POST라서 `EventSource`를 쓸 수 없다. `fetch` + `ReadableStream`으로 프레임을 직접 파싱한다.
이벤트 순서는 `evidence → token* → done`이고, 실패하면 `error`가 온다.
`token`만 이어 붙이고 최종 근거는 `done`의 값으로 덮어쓴다.

## 백엔드 계약 메모

- 엔드포인트에 `response_model`이 없어 OpenAPI에 **응답 스키마가 없다.** `src/lib/types.ts`는
  실행 중인 서버의 실제 응답을 확인해 작성했다. 백엔드 응답이 바뀌면 여기도 같이 고쳐야 한다.
- `GET /videos/{id}`는 `metadata_embedding`(약 23KB)까지 반환하므로 화면에서 쓰지 않는다.
  단일 영상 상태는 목록 응답과 SSE로 갱신한다.
- 소유하지 않은 리소스는 403이 아니라 **404**가 온다.
- `analysis_status`의 `ready`는 구버전 데이터에만 남아 있는 값으로 `succeeded`와 같게 취급한다.
- `analysis_stage` 어휘는 백엔드 `services.ANALYSIS_MESSAGES`가 원본이다. stage를 추가하면
  `src/lib/types.ts`의 `AnalysisStage`와 `src/lib/format.ts`의 `STAGE_LABEL`을 함께 갱신한다.
