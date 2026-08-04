# Backend API

로컬 주소: `http://127.0.0.1:8000`
대화형 확인: `http://127.0.0.1:8000/docs`

| Method | Path | 역할 | 상태 |
| --- | --- | --- | --- |
| `GET` | `/health` | 로컬 서버와 큐 종류 확인 | 200 |
| `GET` | `/auth/me` | 현재 브라우저의 익명 작업공간과 코드 확인 | 200 |
| `POST` | `/auth/workspace` | 작업공간 코드로 현재 브라우저를 기존 작업공간에 연결 | 200 |
| `POST` | `/auth/new-workspace` | 새 익명 작업공간으로 전환 | 201 |
| `POST` | `/channels` | YouTube 채널 URL 등록 | 201 |
| `GET` | `/channels` | 등록 채널 목록 | 200 |
| `GET` | `/channels/{channel_id}/videos` | 선택 채널의 메타데이터 목록 | 200 |
| `POST` | `/channels/{channel_id}/scan` | `yt-dlp --flat-playlist` 메타데이터 탐색 작업 등록 | 202 |
| `POST` | `/channels/{channel_id}/videos` | 로컬 테스트용 영상 메타데이터 추가 | 201 |
| `GET` | `/videos/{video_id}` | 영상 상태와 오류 확인 | 200 |
| `POST` | `/videos/{video_id}/analyze` | 자막/STT 분석 작업 등록 | 202 |
| `GET` | `/videos/{video_id}/events` | 세션 작업공간 소유 영상의 분석 상태 SSE 구독 | 200 |
| `POST` | `/videos/{video_id}/transcript` | 로컬 테스트용 시간 자막 입력 | 204 |
| `POST` | `/recommendations` | 제목·설명 embedding 기반 영상 추천 | 200 |
| `POST` | `/chat` | 분석된 자막 검색 후 답변과 시간 근거 반환 | 200 |

## 핵심 요청 예시

```json
POST /recommendations
{ "query": "FastAPI RAG", "limit": 5 }
```

```json
POST /chat
{ "query": "RAG 구축 순서를 설명해줘", "limit": 3 }
```

```json
POST /auth/workspace
{ "workspace_code": "ABCD2345" }
```

`/recommendations`의 결과는 `basis: "제목과 영상 설명의 embedding 유사도"`를 포함한다. `/chat`의 `evidence[]`는 각 `start_seconds`, `end_seconds`, `url`을 포함한다.

## 분석 상태 SSE

`POST /videos/{video_id}/analyze`가 `202 { "job_id": 314, "status": "queued" }`를 반환한 뒤, 같은 브라우저는 다음 endpoint를 `EventSource`로 연다.

```http
GET /videos/12/events
Accept: text/event-stream
```

이 endpoint는 URL query string에 사용자 식별자나 비밀값을 넣지 않는다. 기존 세션 쿠키로 작업공간 소유권을 확인하며, 소유하지 않은 영상 ID는 `404`를 반환한다.

최초 연결 시 현재 상태를 즉시 보내고, 이후 `jobs` 또는 `videos`의 상태·진행 단계가 바뀔 때만 아래 형식의 event를 보낸다. `retry: 3000`과 약 20초 간격의 heartbeat comment도 보낸다.

```text
retry: 3000

event: analysis_status
data: {"video_id":12,"job_id":314,"status":"running","progress":{"stage":"embedding","message":"자막 구간의 embedding을 생성하고 있습니다."},"error":null,"updated_at":"2026-08-04T05:42:28.123Z"}
```

`status`는 `queued`, `running`, `succeeded`, `failed` 중 하나다. `progress.stage`는 `queued`, `downloading_caption`, `transcribing`, `chunking`, `embedding`, `completed`, `failed` 중 하나다. terminal event인 `succeeded` 또는 `failed`를 보낸 뒤 stream은 종료된다.

Worker는 FastAPI에 HTTP callback을 보내지 않는다. Worker가 `jobs`와 `videos`에 상태를 기록하면 SSE endpoint가 DB를 1초 간격으로 읽어 브라우저에 전달한다.
