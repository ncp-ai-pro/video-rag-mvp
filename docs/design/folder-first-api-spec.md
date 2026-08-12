# Folder-First UI API Spec

목적: `docs/design/video-rag-chat-first-mockup.html`의 새 화면 구조를 실제 API로 연결하기 위한 명세 초안이다. 현재 구현된 API는 유지하고, 화면 전환에 필요한 API만 추가한다.

## 현재 API 구조 판단

현재 백엔드는 작업공간 안에서 `channels -> videos -> analysis/chat` 순서로 동작한다.

| 영역 | 현재 API | 현재 동작 | 새 UI와의 차이 |
| --- | --- | --- | --- |
| 작업공간 | `GET /auth/me`, `POST /auth/workspace`, `POST /auth/new-workspace` | 익명 workspace cookie 기반 | 그대로 사용 가능 |
| 채널 | `POST /channels`, `GET /channels`, `POST /channels/{channel_id}/scan` | 채널을 등록하고 채널 영상 메타데이터를 수집 | 새 UI에서는 채널이 메인 탐색 단위가 아니라 폴더의 후보 수집 소스 |
| 영상 목록 | `GET /channels/{channel_id}/videos` | 특정 채널의 영상만 반환 | 폴더별 영상 목록을 바로 보여줄 수 없음 |
| 단일 영상 추가 | `POST /channels/{channel_id}/videos` | 로컬 테스트용. `channel_id` 필수 | 사용자가 링크 하나를 폴더에 바로 추가하는 UX와 맞지 않음 |
| 영상 분석 | `POST /videos/{video_id}/analyze`, `GET /videos/{video_id}/events` | 기존 영상 ID를 분석하고 SSE로 상태 제공 | 그대로 사용 가능. 단, 폴더 편입 후 호출되어야 함 |
| 채팅 | `POST /chat/stream`, `POST /chat`, `GET /chat/history` | `video_id`가 있으면 단일 영상, 없으면 workspace 전체 | 폴더 단위 RAG scope가 없음 |
| 추천 | `POST /recommendations` | workspace 메타데이터 embedding 검색 | 폴더 후보/수집 후보의 상태와 연결되지 않음 |

근거 코드:

- `app/main.py`의 `required_video()`는 `videos JOIN channels`로 workspace 소유권을 확인한다. 즉 영상은 현재 채널 소속이어야 한다.
- `app/db.py`의 `videos.channel_id`는 `NOT NULL`이다. 단일 URL로 독립 영상을 만들 구조가 없다.
- `app/routers/chat.py`의 `ChatRequest.video_id`는 optional이지만 `folder_id`가 없다. 폴더 범위 채팅은 현재 표현할 수 없다.

## 결론

API 추가가 필요하다. 다만 기존 API를 제거할 필요는 없다.

권장 방향은 다음과 같다.

1. 기존 `/auth/*`, `/videos/{video_id}/analyze`, `/videos/{video_id}/events`, `/chat/stream`은 유지한다.
2. 새 UI의 1차 탐색 단위를 `folder`로 추가한다.
3. 채널은 좌측 메인 목록이 아니라 `folder` 안의 `channel source` 또는 `collection source`로 낮춘다.
4. 단일 영상 URL 추가는 `folder`에 직접 붙는 API로 제공한다.
5. 수집 후보에서 `분석 후 추가`를 누르면 후보가 `folder_videos`로 편입되고 기존 analysis job이 실행된다.
6. 채팅은 `folder_id`를 받아 폴더 안의 분석 완료 영상만 검색하도록 확장한다.

## 데이터 모델 초안

### folders

사용자가 보는 최상위 작업 단위다.

| column | type | 설명 |
| --- | --- | --- |
| `id` | integer/bigint | folder id |
| `user_id` | integer/bigint | workspace owner |
| `name` | text | 예: `LangGraph RAG` |
| `description` | text nullable | 폴더 설명 |
| `color` | text nullable | UI accent token. 예: `amber` |
| `created_at` | timestamp | 생성 시각 |
| `updated_at` | timestamp nullable | 수정 시각 |

제약:

- `UNIQUE(user_id, name)` 권장
- `ON DELETE CASCADE`로 workspace 삭제 시 같이 삭제

### folder_videos

한 영상이 여러 폴더에 들어갈 수 있게 하는 join table이다.

| column | type | 설명 |
| --- | --- | --- |
| `folder_id` | integer/bigint | folder id |
| `video_id` | integer/bigint | video id |
| `source` | text | `direct`, `candidate`, `channel_scan`, `manual` |
| `position` | integer nullable | 폴더 안 정렬 |
| `added_at` | timestamp | 추가 시각 |

제약:

- `PRIMARY KEY(folder_id, video_id)` 또는 `UNIQUE(folder_id, video_id)`

### channel_sources

채널 탐색 기능을 폴더 안의 보조 수집 소스로 분리한다. 초기 구현에서는 기존 `channels` 테이블에 `folder_id`를 추가하거나 별도 테이블로 분리한다.

| column | type | 설명 |
| --- | --- | --- |
| `id` | integer/bigint | source id |
| `user_id` | integer/bigint | workspace owner |
| `folder_id` | integer/bigint nullable | 특정 폴더에 연결된 수집 소스 |
| `url` | text | YouTube channel URL |
| `name` | text nullable | 표시 이름 |
| `last_scanned_at` | timestamp nullable | 마지막 수집 |
| `created_at` | timestamp | 생성 시각 |

### folder_candidates

채널 수집 또는 추천에서 나온 “분석 전 후보”를 담는다. 후보가 실제 `videos`에 이미 존재하면 `video_id`를 연결하고, 아직 메타데이터만 있으면 `platform_video_id`와 URL만 가진다.

| column | type | 설명 |
| --- | --- | --- |
| `id` | integer/bigint | candidate id |
| `folder_id` | integer/bigint | folder id |
| `channel_source_id` | integer/bigint nullable | 후보 출처 |
| `video_id` | integer/bigint nullable | 이미 `videos`로 만들어진 경우 |
| `platform_video_id` | text | YouTube video id |
| `title` | text | 제목 |
| `description` | text | 설명 |
| `url` | text | 영상 URL |
| `thumbnail_url` | text nullable | 썸네일 |
| `duration_seconds` | integer nullable | 길이 |
| `score` | real nullable | 추천/검색 점수 |
| `basis` | text nullable | 추천 근거 |
| `status` | text | `new`, `queued`, `added`, `dismissed` |
| `created_at` | timestamp | 생성 시각 |

## videos 테이블 조정

현재 `videos.channel_id NOT NULL` 때문에 단일 영상 URL 추가가 어렵다.

권장안:

- `videos.user_id`를 추가한다.
- `videos.channel_id`를 nullable로 바꾼다.
- 소유권 확인은 `videos.user_id = workspace.id`로 처리한다.
- 채널에서 온 영상은 `channel_id`를 유지한다.
- URL 단독 추가 영상은 `channel_id = NULL`, `source_type = 'direct'` 같은 필드를 둔다.

빠른 MVP 대안:

- workspace마다 내부용 `manual` channel을 자동 생성한다.
- `POST /folders/{folder_id}/videos`가 내부적으로 그 channel에 `upsert_video()`를 호출한다.
- 이후 `folder_videos`에 연결한다.
- 이 방식은 기존 `required_video()`와 worker를 덜 건드린다.

## API 명세

### Folder

#### `GET /folders`

현재 workspace의 폴더 목록과 카운트를 반환한다.

Response `200`

```json
[
  {
    "id": 1,
    "name": "LangGraph RAG",
    "description": "조건부 엣지와 RAG 실습 영상 모음",
    "color": "amber",
    "video_count": 12,
    "ready_count": 9,
    "running_count": 1,
    "candidate_count": 8,
    "updated_at": "2026-08-12T04:10:00Z"
  }
]
```

#### `POST /folders`

폴더를 만든다. 첫 진입 화면에서 링크를 넣고 분석을 시작할 때도 자동 생성에 사용한다.

Request

```json
{
  "name": "LangGraph RAG",
  "description": "LangGraph 기반 RAG 강의 모음",
  "color": "amber"
}
```

Response `201`

```json
{
  "id": 1,
  "name": "LangGraph RAG",
  "description": "LangGraph 기반 RAG 강의 모음",
  "color": "amber",
  "created_at": "2026-08-12T04:10:00Z"
}
```

Errors:

- `409`: 같은 workspace에 같은 이름의 folder가 이미 있음
- `422`: 이름 누락 또는 길이 초과

#### `GET /folders/{folder_id}`

폴더 상세, 영상 카운트, 연결된 수집 소스 요약을 반환한다.

#### `PATCH /folders/{folder_id}`

폴더 이름, 설명, 색상, 정렬 정보를 수정한다.

#### `DELETE /folders/{folder_id}`

폴더만 삭제한다. 기본 정책은 영상 원본과 분석 결과는 삭제하지 않는다.

Query option:

- `delete_videos=false`: 기본값. `folder_videos` 연결만 삭제
- `delete_videos=true`: 해당 폴더에만 연결된 영상이면 원본까지 삭제

### Folder Videos

#### `GET /folders/{folder_id}/videos`

폴더 안의 영상 목록을 반환한다. 새 mockup의 “폴더 영상” 박스가 이 API를 사용한다.

Query:

- `status`: `all`, `metadata_only`, `queued`, `running`, `ready`, `failed`
- `q`: 제목/채널/설명 검색
- `limit`: 기본 `30`, 최대 `100`
- `cursor`: 다음 페이지 cursor

Response `200`

```json
{
  "items": [
    {
      "id": 12,
      "folder_id": 1,
      "title": "LangGraph RAG에서 Conditional Edge를 쓰는 이유",
      "url": "https://www.youtube.com/watch?v=abc123",
      "thumbnail_url": "https://i.ytimg.com/vi/abc123/hqdefault.jpg",
      "duration_seconds": 1122,
      "source": "candidate",
      "source_label": "NAVER Cloud AI",
      "analysis_status": "ready",
      "analysis_stage": "completed",
      "analysis_message": "분석 완료",
      "evidence_count": 12,
      "added_at": "2026-08-12T04:10:00Z",
      "analyzed_at": "2026-08-12T04:14:00Z"
    }
  ],
  "next_cursor": null
}
```

UI 표시 규칙:

- `ready` 또는 `succeeded`: `분석 완료`
- `queued`: `대기 중`
- `running`: `분석 중`
- `failed`: `실패`
- `metadata_only`: `수집 완료`

#### `POST /folders/{folder_id}/videos`

영상 링크를 폴더에 직접 추가한다. 새 mockup의 “새 영상 링크 추가”와 첫 시작 화면의 “분석 시작”이 이 API를 사용한다.

Request

```json
{
  "url": "https://www.youtube.com/watch?v=abc123",
  "analyze": true,
  "title": null
}
```

Response `201`

```json
{
  "video": {
    "id": 12,
    "title": "LangGraph RAG에서 Conditional Edge를 쓰는 이유",
    "url": "https://www.youtube.com/watch?v=abc123",
    "thumbnail_url": "https://i.ytimg.com/vi/abc123/hqdefault.jpg",
    "analysis_status": "queued"
  },
  "folder_video": {
    "folder_id": 1,
    "video_id": 12,
    "source": "direct",
    "added_at": "2026-08-12T04:10:00Z"
  },
  "job": {
    "job_id": 314,
    "status": "queued"
  }
}
```

동작:

1. URL에서 `platform_video_id`를 추출한다.
2. 메타데이터를 가져오거나 최소 메타데이터로 `videos`를 만든다.
3. `folder_videos`에 연결한다.
4. `analyze=true`이면 기존 `enqueue_analysis_job(video_id)`를 호출한다.

Errors:

- `404`: folder가 현재 workspace에 없음
- `409`: 이미 폴더에 있는 영상
- `422`: 지원하지 않는 URL
- `502`: 외부 메타데이터 조회 실패. 단, 최소 메타데이터 저장 정책이면 `201`로 반환하고 `metadata_status=partial`을 둔다.

#### `POST /folders/{folder_id}/videos/{video_id}`

이미 workspace에 있는 영상을 현재 폴더에 추가한다.

Request

```json
{
  "analyze": false,
  "source": "manual"
}
```

Response `201`

```json
{
  "folder_id": 1,
  "video_id": 12,
  "source": "manual",
  "added_at": "2026-08-12T04:10:00Z"
}
```

#### `DELETE /folders/{folder_id}/videos/{video_id}`

폴더에서 영상을 제거한다. 영상 원본과 분석 결과는 기본적으로 유지한다.

#### `PATCH /folders/{folder_id}/videos/{video_id}`

폴더 안 정렬 또는 메모성 필드를 수정한다.

Request

```json
{
  "position": 3
}
```

### Analysis

기존 API를 유지한다.

#### `POST /videos/{video_id}/analyze`

현재 그대로 사용 가능하다. 다만 새 UI에서는 단독으로 직접 호출하기보다 `POST /folders/{folder_id}/videos` 또는 후보 편입 API가 내부적으로 호출하는 흐름이 자연스럽다.

#### `GET /videos/{video_id}/events`

현재 그대로 사용 가능하다. 폴더 화면에서 분석 상태를 구독할 때 이 endpoint를 사용한다.

추가 wrapper는 선택 사항이다.

```http
GET /folders/{folder_id}/videos/{video_id}/events
```

이 wrapper를 만들면 frontend가 “현재 폴더에 있는 영상만 구독”이라는 의도를 명확히 표현할 수 있다. 내부 구현은 기존 `/videos/{video_id}/events`와 동일하게 재사용한다.

### Folder Chat

#### `GET /folders/{folder_id}/chat/history`

폴더 단위 채팅 기록을 반환한다.

Query:

- `limit`: 기본 `20`, 최대 `100`
- `before_id`: cursor
- `video_id`: 선택값. 있으면 폴더 안 특정 영상 채팅

Response `200`

```json
{
  "items": [
    {
      "id": 51,
      "role": "user",
      "content": "Conditional Edge가 왜 필요해?",
      "video_id": null,
      "created_at": "2026-08-12T04:20:00Z"
    }
  ],
  "next_before_id": 42
}
```

DB 변경:

- `chat_messages.folder_id` 추가 권장
- `video_id`와 `folder_id`를 둘 다 nullable로 둘 수 있음
- `folder_id`만 있으면 폴더 전체 채팅, `folder_id + video_id`면 폴더 안 단일 영상 채팅

#### `POST /folders/{folder_id}/chat/stream`

폴더 안의 분석 완료 영상만 검색해 답변한다. 새 mockup의 대형 챗봇 기본 입력창이 이 API를 사용한다.

Request

```json
{
  "query": "이 폴더 영상들 기준으로 LangGraph Conditional Edge를 설명해줘",
  "video_id": null,
  "limit": 3,
  "evidence_mode": "simple"
}
```

Response `200 text/event-stream`

```text
retry: 3000

event: evidence
data: {"evidence":[{"video_id":12,"title":"LangGraph RAG에서 Conditional Edge를 쓰는 이유","start_seconds":233.1,"end_seconds":251.4,"quote":"..."}]}

event: token
data: {"text":"Conditional Edge는 "}

event: done
data: {"evidence":[...]}
```

검색 scope:

- `video_id`가 없으면 `folder_videos`에 연결된 분석 완료 영상 전체
- `video_id`가 있으면 해당 영상이 `folder_id`에 연결되어 있는지 확인 후 단일 영상

기존 `/chat/stream`은 유지한다. 새 endpoint는 folder scope만 추가한다.

### Channel Sources and Candidates

채널 탐색은 별도 화면 또는 폴더 하단 후보 박스에서 호출한다. 메인 IA에서는 `channels` 대신 `folder channel_sources`로 표현한다.

#### `GET /folders/{folder_id}/channel-sources`

폴더에 연결된 수집 채널 목록을 반환한다.

Response `200`

```json
[
  {
    "id": 7,
    "folder_id": 1,
    "url": "https://www.youtube.com/@navercloud",
    "name": "NAVER Cloud AI",
    "last_scanned_at": "2026-08-12T03:10:00Z",
    "candidate_count": 8
  }
]
```

#### `POST /folders/{folder_id}/channel-sources`

폴더에 채널 수집 소스를 추가한다.

Request

```json
{
  "url": "https://www.youtube.com/@navercloud",
  "name": "NAVER Cloud AI",
  "auto_scan": true
}
```

Response `201`

```json
{
  "id": 7,
  "folder_id": 1,
  "url": "https://www.youtube.com/@navercloud",
  "name": "NAVER Cloud AI",
  "scan_job": {
    "job_id": 410,
    "status": "queued"
  }
}
```

#### `POST /folders/{folder_id}/channel-sources/{source_id}/scan`

채널 수집을 다시 실행한다.

Response `202`

```json
{
  "job_id": 410,
  "status": "queued"
}
```

#### `GET /folders/{folder_id}/candidates`

폴더에 추천된 분석 후보 영상을 반환한다. 새 mockup의 “수집 후보” 탭이 이 API를 사용한다.

Query:

- `q`: 후보 검색
- `status`: `new`, `queued`, `added`, `dismissed`, `all`
- `limit`: 기본 `20`, 최대 `100`
- `cursor`: 다음 페이지 cursor

Response `200`

```json
{
  "items": [
    {
      "id": 91,
      "folder_id": 1,
      "title": "LangGraph RAG 조건부 라우팅 실습",
      "url": "https://www.youtube.com/watch?v=xyz987",
      "thumbnail_url": "https://i.ytimg.com/vi/xyz987/hqdefault.jpg",
      "duration_seconds": 1650,
      "source_label": "NAVER Cloud AI",
      "score": 0.82,
      "basis": "폴더 주제와 제목/설명 embedding 유사도",
      "status": "new"
    }
  ],
  "next_cursor": null
}
```

#### `POST /folders/{folder_id}/candidates/{candidate_id}/analyze`

후보 카드의 `분석 후 추가` 버튼이 호출한다. 후보를 현재 폴더 영상으로 편입하고 분석 job을 등록한다.

Request

```json
{
  "analyze": true
}
```

Response `202`

```json
{
  "candidate": {
    "id": 91,
    "status": "queued"
  },
  "video": {
    "id": 34,
    "title": "LangGraph RAG 조건부 라우팅 실습",
    "analysis_status": "queued"
  },
  "folder_video": {
    "folder_id": 1,
    "video_id": 34,
    "source": "candidate"
  },
  "job": {
    "job_id": 415,
    "status": "queued"
  }
}
```

동작:

1. 후보가 현재 workspace와 folder에 속하는지 확인한다.
2. 후보 메타데이터로 `videos`를 upsert한다.
3. `folder_videos`에 연결한다.
4. `folder_candidates.status`를 `queued` 또는 `added`로 바꾼다.
5. `analyze=true`이면 기존 analysis job을 등록한다.

#### `PATCH /folders/{folder_id}/candidates/{candidate_id}`

후보 숨김, 보류, 메모 상태 변경에 사용한다.

Request

```json
{
  "status": "dismissed"
}
```

### Recommendations

기존 `POST /recommendations`는 유지하되, 새 UI에서는 폴더 문맥을 명시하는 endpoint를 추가한다.

#### `POST /folders/{folder_id}/recommendations`

Request

```json
{
  "query": "LangGraph Conditional Edge",
  "limit": 8,
  "include_candidates": true
}
```

Response `200`

```json
{
  "query": "LangGraph Conditional Edge",
  "items": [
    {
      "candidate_id": 91,
      "video_id": null,
      "title": "LangGraph RAG 조건부 라우팅 실습",
      "url": "https://www.youtube.com/watch?v=xyz987",
      "basis": "폴더 주제와 제목/설명 embedding 유사도",
      "score": 0.82
    }
  ],
  "notice": "추천은 제목과 영상 설명의 embedding 유사도 기반이며 영상 내용을 검증하지 않습니다."
}
```

## 첫 시작 화면 API 흐름

새 사용자가 처음 들어왔을 때 추천 흐름:

1. `GET /auth/me`
2. 폴더가 없으면 home view 표시
3. 사용자가 YouTube URL 입력
4. frontend가 폴더명을 제안하거나 사용자가 직접 입력
5. `POST /folders`
6. `POST /folders/{folder_id}/videos` with `{ "url": "...", "analyze": true }`
7. `GET /videos/{video_id}/events`로 분석 상태 표시
8. 완료 후 `POST /folders/{folder_id}/chat/stream` 사용

폴더명 자동 추천을 서버에서 하고 싶으면 다음 API를 추가할 수 있다.

#### `POST /folders:suggest`

Request

```json
{
  "url": "https://www.youtube.com/watch?v=abc123"
}
```

Response `200`

```json
{
  "suggested_name": "LangGraph RAG",
  "reason": "영상 제목과 설명에서 LangGraph, RAG 키워드가 반복됨"
}
```

MVP에서는 이 API 없이 frontend heuristic으로 시작해도 된다.

## 최소 구현 범위

새 mockup을 실제 UI로 붙이기 위한 최소 API는 아래 6개다.

| 우선순위 | Method | Path | 이유 |
| --- | --- | --- | --- |
| 1 | `GET` | `/folders` | 좌측 폴더 rail 렌더링 |
| 1 | `POST` | `/folders` | 첫 시작 및 새 폴더 생성 |
| 1 | `GET` | `/folders/{folder_id}/videos` | 폴더 영상 박스 렌더링 |
| 1 | `POST` | `/folders/{folder_id}/videos` | 단일 영상 링크 추가 및 즉시 분석 |
| 1 | `POST` | `/folders/{folder_id}/chat/stream` | 대형 챗봇의 폴더 범위 RAG |
| 2 | `GET` | `/folders/{folder_id}/candidates` | 수집 후보 탭 |
| 2 | `POST` | `/folders/{folder_id}/candidates/{candidate_id}/analyze` | 후보를 분석 후 현재 폴더로 편입 |
| 3 | `POST` | `/folders/{folder_id}/channel-sources` | 채널 탐색을 폴더 보조 기능으로 이동 |

## 기존 API 호환 정책

기존 endpoint는 삭제하지 않는다.

| 기존 API | 정책 |
| --- | --- |
| `/channels` | 당분간 유지. 새 UI에서는 `channel-sources` 구현 전까지 내부 adapter로 사용 가능 |
| `/channels/{channel_id}/videos` | 유지. 채널 상세/디버그/마이그레이션용 |
| `/videos/{video_id}/analyze` | 유지. 새 API 내부에서 재사용 |
| `/videos/{video_id}/events` | 유지. 새 UI에서 그대로 구독 가능 |
| `/chat/stream` | 유지. workspace 전체 또는 단일 영상 fallback |
| `/recommendations` | 유지. folder-aware 추천 추가 전 fallback |

## 구현 단계 제안

### Phase 1: Folder shell

- `folders`, `folder_videos` 테이블 추가
- `GET /folders`, `POST /folders`
- `GET /folders/{folder_id}/videos`
- `POST /folders/{folder_id}/videos`
- 단일 영상 직접 추가는 빠른 MVP 대안으로 내부 `manual` channel을 사용

### Phase 2: Folder chat

- `chat_messages.folder_id` 추가
- `POST /folders/{folder_id}/chat/stream`
- `GET /folders/{folder_id}/chat/history`
- `find_evidence()`에 folder scope filter 추가

### Phase 3: Candidates

- `channel_sources` 또는 기존 `channels.folder_id` 추가
- `folder_candidates` 추가
- `GET /folders/{folder_id}/candidates`
- `POST /folders/{folder_id}/candidates/{candidate_id}/analyze`

### Phase 4: Schema cleanup

- `videos.user_id` 추가
- `videos.channel_id` nullable 전환
- `required_video()`를 `videos.user_id` 기준으로 단순화
- 기존 channel 기반 데이터는 `channel_id` 유지

## Frontend 연결 기준

새 HTML 화면 기준으로 frontend 상태는 다음 리소스에 매핑한다.

| UI 영역 | 필요한 API |
| --- | --- |
| 첫 시작 URL 입력 | `POST /folders`, `POST /folders/{folder_id}/videos` |
| 좌측 접이식 폴더 rail | `GET /folders` |
| 폴더 영상 박스 | `GET /folders/{folder_id}/videos` |
| 새 영상 링크 추가 | `POST /folders/{folder_id}/videos` |
| 수집 후보 탭 | `GET /folders/{folder_id}/candidates` |
| 후보의 `분석 후 추가` | `POST /folders/{folder_id}/candidates/{candidate_id}/analyze` |
| 분석 진행 애니메이션 | `GET /videos/{video_id}/events` |
| 대형 챗봇 | `POST /folders/{folder_id}/chat/stream` |
| 근거/플레이어 패널 | `POST /folders/{folder_id}/chat/stream`의 `evidence[]` |

