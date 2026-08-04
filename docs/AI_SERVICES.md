# AI 서비스 연동 문서

## 로컬과 NCP 모드

| 기능 | 로컬 기본값 | NCP 전환 값 | 사용 시점 |
| --- | --- | --- | --- |
| 영상 메타데이터 embedding | 해시 기반 mock | CLOVA Studio Embedding v2 | 모든 영상 메타데이터 탐색 후 |
| 자막 chunk embedding | 해시 기반 mock | CLOVA Studio Embedding v2 | 사용자가 분석한 영상만 |
| RAG 답변 | 고정된 로컬 안내문 | CLOVA Studio Chat Completions v3 | 분석 완료 영상 질문 시 |
| 자막 없는 영상 STT | 미연결, 오류 기록 | CLOVA Speech 장문 인식 | 자막 수집 실패 시 |

작업공간 세션은 AI 서비스와 분리된 FastAPI 서버 기능이다. 브라우저 식별자나 기기 지문을 AI 요청에 보내지 않는다.

## CLOVA Studio

`EMBEDDING_PROVIDER=clova`, `CHAT_PROVIDER=clova`, `CLOVASTUDIO_API_KEY=<YOUR_CLOVA_STUDIO_API_KEY>`를 설정하면 전환된다.

- Embedding v2: `POST https://clovastudio.stream.ntruss.com/v1/api-tools/embedding/v2/`
- Chat Completions v3: `POST https://clovastudio.stream.ntruss.com/v3/chat-completions/{modelName}`
- 구현 파일: `app/services.py`의 `embedding()`과 `answer()`

키는 `.env`, 소스코드, 브라우저 JavaScript에 넣지 않는다. FastAPI Worker의 환경 변수로만 주입한다.

## CLOVA Speech

자막이 없는 영상은 `yt-dlp`로 선택한 영상의 오디오만 내려받고, CLOVA Speech 장문 인식 API에 보낸다. 장문 인식 결과는 JSON 또는 SRT로 받아 `start_seconds`, `end_seconds`, `text` 형태로 변환한 후 RAG chunk로 저장한다.

현재 로컬 코드의 `app/worker.py`는 실제 자막 VTT 수집까지 구현되어 있다. 장문 STT는 NCP 콘솔에서 발급받는 Invoke URL·API key, Object Storage 결과 저장 또는 callback URL 설정이 필요하므로 아직 호출하지 않는다. 이 상태에서는 `subtitle_not_found`가 `jobs.error_message`와 `videos.analysis_error`에 기록된다.

## NCP 배포 교체 지점

| 로컬 | NCP private server |
| --- | --- |
| SQLite | Cloud DB for PostgreSQL + `pgvector` |
| SQLite `jobs` Worker | Cloud DB for Redis 기반 큐 Worker |
| `data/downloads/` | Object Storage private bucket |
| mock embedding/chat | CLOVA Studio service app key |
