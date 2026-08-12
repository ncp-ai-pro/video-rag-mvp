# Backend API

API 주소: `http://127.0.0.1:8000` · Chat 주소: `http://127.0.0.1:8001`
대화형 확인: API는 `http://127.0.0.1:8000/docs`, Chat은 `http://127.0.0.1:8001/docs`

| Method | Path | 역할 | 상태 |
| --- | --- | --- | --- |
| `GET` | `/health` | 로컬 서버와 큐 종류 확인 | 200 |
| `GET` | `/auth/me` | 현재 브라우저의 익명 작업공간과 코드 확인 | 200 |
| `POST` | `/auth/workspace` | 작업공간 코드로 현재 브라우저를 기존 작업공간에 연결 | 200 |
| `POST` | `/auth/new-workspace` | 새 익명 작업공간으로 전환 | 201 |
| `GET` | `/folders` | 현재 작업공간의 지식 폴더 목록과 영상/후보 카운트 조회 | 200 |
| `POST` | `/folders` | 지식 폴더 생성 | 201 |
| `GET` | `/folders/{folder_id}` | 폴더 상세, 영상 요약, 채널 소스 요약 조회 | 200 |
| `PATCH` | `/folders/{folder_id}` | 폴더 이름, 설명, 색상 수정 | 200 |
| `DELETE` | `/folders/{folder_id}` | 폴더 삭제. 영상 원본은 유지 | 204 |
| `GET` | `/folders/{folder_id}/videos` | 폴더에 들어간 분석/수집 영상 목록 조회 | 200 |
| `POST` | `/folders/{folder_id}/videos` | YouTube URL을 폴더에 직접 추가하고 선택적으로 분석 작업 등록 | 201 |
| `POST` | `/folders/{folder_id}/videos/{video_id}` | 기존 작업공간 영상을 폴더에 연결 | 201 |
| `DELETE` | `/folders/{folder_id}/videos/{video_id}` | 폴더에서 영상 연결 제거 | 204 |
| `GET` | `/folders/{folder_id}/channel-sources` | 폴더에 연결된 채널 수집 소스 목록 조회 | 200 |
| `POST` | `/folders/{folder_id}/channel-sources` | 폴더에 채널 수집 소스 추가 | 201 |
| `POST` | `/folders/{folder_id}/channel-sources/{source_id}/scan` | 폴더 채널 소스의 메타데이터 수집 작업 등록 | 202 |
| `GET` | `/folders/{folder_id}/candidates` | 폴더 채널 소스에서 수집됐지만 아직 폴더에 편입되지 않은 후보 조회 | 200 |
| `POST` | `/folders/{folder_id}/candidates/{candidate_id}/analyze` | 후보 영상을 폴더에 편입하고 분석 작업 등록 | 202 |
| `POST` | `/folders/{folder_id}/recommendations` | 폴더 화면용 메타데이터 추천 조회 | 200 |
| `POST` | `/folders/{folder_id}/chat` | 폴더 안 분석 완료 영상만 검색해 완료 답변 반환 | 200 |
| `POST` | `/folders/{folder_id}/chat/stream` | 폴더 안 분석 완료 영상만 검색해 token SSE 반환 | 200 |
| `GET` | `/folders/{folder_id}/chat/history` | 폴더 단위 채팅 기록 조회 | 200 |
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
| `POST` | Chat Server `/chat` | 분석된 자막 검색 후 완료 답변과 시간 근거 반환 | 200 |
| `POST` | Chat Server `/chat/stream` | 분석된 자막 검색 후 token SSE와 시간 근거 반환 | 200 |
| `GET` | Chat Server `/chat/history` | 선택 영상 또는 일반 대화의 cursor 기반 채팅 기록 조회 | 200 |

## 핵심 요청 예시

```json
POST /recommendations
{ "query": "FastAPI RAG", "limit": 5 }
```

```json
POST /chat
{ "query": "RAG 구축 순서를 설명해줘", "video_id": 12, "limit": 3, "evidence_mode": "simple" }
```

```json
POST /auth/workspace
{ "workspace_code": "ABCD2345" }
```

```json
POST /folders
{ "name": "LangGraph RAG", "description": "조건부 엣지와 RAG 실습 모음", "color": "amber" }
```

```json
POST /folders/1/videos
{ "url": "https://www.youtube.com/watch?v=abc123", "analyze": true }
```

```json
POST /folders/1/chat
{ "query": "이 폴더 영상 기준으로 RAG 흐름을 설명해줘", "limit": 3, "evidence_mode": "simple" }
```

`/recommendations`의 결과는 `basis: "제목과 영상 설명의 embedding 유사도"`를 포함한다. `/chat`의 `evidence[]`는 각 `start_seconds`, `end_seconds`, `url`을 포함한다. `video_id`를 보내면 Chat Server가 현재 작업공간 소유 영상인지 확인한 뒤 해당 영상의 자막과 대화 기록만 사용한다. 다른 작업공간의 `video_id`는 `404`를 반환한다.

폴더 API는 기존 채널/영상 API를 제거하지 않고 그 위에 폴더 연결을 추가한다. `POST /folders/{folder_id}/videos`는 현재 구현에서 내부 `직접 추가 영상` channel을 사용해 `videos.channel_id NOT NULL` 구조와 기존 Worker를 그대로 재사용한다. `GET /folders/{folder_id}/candidates`의 `candidate_id`는 현재 구현 기준으로 `video_id`와 같다. 채널 소스에서 수집된 영상 중 아직 `folder_videos`에 연결되지 않은 영상을 후보로 노출한다.

`evidence_mode`는 다음 값을 받는다.

| 값 | 동작 |
| --- | --- |
| `simple` | 검색 score 1등 근거 카드만 `is_primary=true`로 표시 |
| `precise` | token overlap으로 근거 quote 내부 핵심 문장을 `highlight.method=query_token_overlap`으로 표시 |
| `ultra` | query와 quote 내부 문장 embedding similarity로 핵심 문장을 `highlight.method=sentence_embedding_similarity`로 표시 |

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

## Chat 응답 스트리밍

`POST /chat`의 JSON 계약은 유지한다. 화면은 Chat Server의 `POST /chat/stream`을 `fetch()`로 호출하고 `text/event-stream` 응답을 읽는다. `EventSource`는 GET 전용이므로 이 endpoint에는 사용하지 않는다. `video_id`가 있으면 user/assistant 메시지는 `chat_messages.video_id`에 함께 저장되고, `GET /chat/history?video_id=12`는 해당 영상의 대화만 반환한다.

```text
retry: 3000

event: evidence
data: {"evidence":[...]}

event: token
data: {"text":"자막 근거를 "}

event: done
data: {"evidence":[...]}
```

`CHAT_PROVIDER=clova`이면 Chat Server가 CLOVA Studio v3의 `Accept: text/event-stream` token 응답을 내부 SSE 형식으로 중계한다. `mock` 모드도 동일한 이벤트 순서로 짧은 token 조각을 보낸다. provider 호출 중 오류가 나면 `event: error`와 `{ "message": "..." }`를 보낸다.
