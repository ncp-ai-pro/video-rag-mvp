# Video RAG MVP (local)

여러 YouTube 채널의 **메타데이터만** 먼저 수집하고, 사용자가 선택한 영상만 자막/음성 기반 RAG로 분석하는 FastAPI 프로토타입입니다.

첫 접속 시 익명 작업공간과 8자리 작업공간 코드가 자동 생성됩니다. 같은 브라우저는 세션 쿠키로 이어지며, 다른 브라우저에서는 화면 상단의 `기존 작업공간 연결`에 코드를 입력해 같은 데이터에 연결합니다.

## 현재 구현 범위

- `POST /channels/{id}/scan`: `yt-dlp --flat-playlist` 작업을 큐에 등록한다. 이 단계는 영상·오디오를 다운로드하지 않는다.
- `POST /recommendations`: 모든 영상의 제목·설명 embedding으로 메타데이터 추천을 반환한다.
- `POST /videos/{id}/analyze`: 선택한 영상만 자막 수집 작업을 큐에 등록한다.
- `POST /videos/{id}/transcript`: 로컬 테스트용 시간 구간 자막을 넣는다.
- Chat Server `POST /chat`: 분석 완료된 자막 chunk만 검색하고, 답변과 최대 3개의 실제 재생 시간 링크를 반환한다. `evidence_mode=ultra`는 근거 내부 문장 embedding similarity로 핵심 문장을 고른다.
- Chat Server `POST /chat/stream`: 같은 근거를 먼저 보내고, Chat 답변 token을 SSE로 중계한다. 기존 `/chat` JSON 응답은 유지한다.
- Chat은 영상별 최근 `CHAT_HISTORY_TURNS`(기본 3턴) 질문·답변을 `chat_messages` 테이블에 저장했다가 다음 CLOVA 요청의 대화 맥락으로 함께 보낸다. 오래된 턴은 같은 영상 스코프 안에서 저장 시점에 바로 정리된다.
- Chat은 워크스페이스별 최근 `CHAT_HISTORY_TURNS`(기본 3턴) 질문·답변을 `chat_messages` 테이블에 저장했다가 다음 CLOVA 요청의 대화 맥락으로 함께 보낸다. 오래된 턴은 저장 시점에 바로 정리된다.
- `REDIS_URL`을 설정하면 Chat Server가 최근 대화 맥락만 Redis에 캐시한다. PostgreSQL `chat_messages`가 원본이며 Redis 장애나 미설정 상태에서는 PostgreSQL 조회로 동작한다.

로컬 기본값은 SQLite `jobs` 테이블과 별도 Worker 프로세스다. `DATABASE_URL`을 설정하면 API·Chat·Worker가 같은 Cloud DB for PostgreSQL에 연결하고, 시작 시 `pgvector` 확장과 1,024차원 RAG vector 스키마를 초기화한다. Worker의 PostgreSQL 작업 선점은 `FOR UPDATE SKIP LOCKED`를 사용한다.

## 실행

Mac에서 다음을 실행한다.

```bash
cd /Users/kimgt/Developer/Project/ncp-ai/video-rag-mvp
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload
```

다른 터미널에서 Chat Server를 실행한다.

```bash
cd /Users/kimgt/Developer/Project/ncp-ai/video-rag-mvp
.venv/bin/uvicorn app.chat_main:app --port 8001 --reload
```

세 번째 터미널에서 Worker를 실행한다.

```bash
cd /Users/kimgt/Developer/Project/ncp-ai/video-rag-mvp
.venv/bin/python -m app.worker
```

## Docker Compose 배포

`DATABASE_URL`이 비어 있으면 API·Chat·Worker는 동일한 SQLite `jobs` 테이블과 `data/`를 공유한다. 이 모드는 로컬 Compose 전용이며 Worker를 한 개만 실행한다. NCP에서 세 역할을 서로 다른 서버에 배포할 때는 반드시 Cloud DB for PostgreSQL URL을 `DATABASE_URL`로 주입한다. 그러면 서버별 Docker 볼륨을 공유할 필요가 없다. 로컬 화면은 `http://localhost:8000`, Chat Server는 `http://localhost:8001`로 실행되며 화면의 질문만 Chat Server로 전달한다.

서버 배포 전에는 `.env`를 Git에 올리지 않고 `.env.example`을 복사해 CLOVA 키와 배포 환경 값을 입력한다. `.env`가 없으면 mock 모드 기본값으로도 컨테이너를 띄울 수 있지만, 실제 NCP AI 호출에는 사용할 수 없다.

```bash
cp .env.example .env
docker compose up -d --build
docker compose ps
```

API는 `http://localhost:8000/health`, Chat Server는 `http://localhost:8001/health`에서 확인할 수 있다. NCP 운영 환경에서는 `.env`에 `DATABASE_URL=postgresql://<USER>:<PASSWORD>@<CLOUD_DB_HOST>:5432/<DATABASE>?sslmode=require`, `SESSION_COOKIE_SECURE=true`, `SESSION_COOKIE_DOMAIN=.example.com`, `CORS_ALLOW_ORIGINS=https://api.example.com`, `CHAT_PUBLIC_ORIGIN=https://chat.example.com`을 설정한다. DB 계정에는 `CREATE EXTENSION vector` 실행 권한이 필요하다. 최근 대화 맥락 조회 부하를 줄일 때만 Chat Server에 `REDIS_URL=redis://<REDIS_HOST>:6379/0`과 `REDIS_CHAT_CACHE_TTL_SECONDS=3600`을 추가한다.

clova voice 캐싱 환경변수 설정 
$env:REDIS_URL = "redis://localhost:6379/0"

### 로컬 PostgreSQL + pgvector로 실행

Mac에서 NCP VPC 내부 Cloud DB 주소에 연결할 수 없을 때는 `compose.local.yml` 오버레이를 사용한다. 이 파일은 Docker 내부 네트워크에 PostgreSQL + pgvector 컨테이너를 만들고, API·Chat·Worker의 `DATABASE_URL`을 `postgres` 서비스로만 덮어쓴다. `.env.local`에 운영 Cloud DB URL이 있어도 로컬 실행에는 사용하지 않는다.

```bash
docker compose -f compose.yml -f compose.local.yml up -d --build
docker compose -f compose.yml -f compose.local.yml ps
```

로컬 DB 데이터까지 초기화하려면 다음 명령을 사용한다. 이 명령은 `video-rag-postgres-data` 볼륨의 모든 로컬 데이터를 삭제한다.

```bash
docker compose -f compose.yml -f compose.local.yml down -v
```

```bash
docker compose logs -f api
docker compose logs -f chat
docker compose logs -f worker
```

GitHub Actions의 수동 CD는 서버의 `NCP_DEPLOY_PATH`에서 같은 `docker compose --env-file .env up -d --build --remove-orphans` 명령을 실행한다. 따라서 서버에는 Docker Compose, 이 저장소의 clone, 그리고 Git에 없는 `.env` 파일이 미리 있어야 한다.

`http://127.0.0.1:8000/docs`에서 API를 호출한다. 기본값은 외부 키 없이 테스트되는 `mock` embedding/Chat 모드다. 이 모드는 API와 검색 경로 확인용이며 CLOVA의 의미 유사도나 답변 품질을 검증하지 않는다.

## 로컬 호출 예시

```bash
curl -X POST http://127.0.0.1:8000/channels \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://www.youtube.com/@GoogleDevelopers","name":"Google Developers"}'

curl -X POST http://127.0.0.1:8000/channels/1/scan
```

스캔이 끝나면 영상 ID를 확인하고 `POST /videos/{video_id}/analyze`를 호출한다. 분석 대상은 그 영상 하나뿐이다.

## CLOVA Studio 연결

`.env.example`의 값을 셸 환경 변수로 설정한다.

```bash
export EMBEDDING_PROVIDER=clova
export CHAT_PROVIDER=clova
export CLOVASTUDIO_API_KEY=<YOUR_CLOVA_STUDIO_API_KEY>
```

Embedding v2는 `POST /v1/api-tools/embedding/v2`를 사용하며, Chat은 `POST /v3/chat-completions/{modelName}`을 사용한다. API key는 `.env`나 코드에 저장하지 않는다.

Worker는 자동 자막의 짧고 중복된 cue를 최대 60초 또는 1,600자 단위 RAG chunk로 병합한 뒤 embedding한다. Test API Key의 Embedding v2 제한(60 QPM)을 넘지 않도록 Worker embedding만 기본 1.5초 간격으로 호출하고, 429는 CLOVA Studio reset header 또는 2·4·8·16·32초 지수 backoff로 최대 5회 재시도한다. 필요하면 `WORKER_RAG_CHUNK_MAX_SECONDS`, `WORKER_RAG_CHUNK_MAX_CHARS`, `WORKER_EMBEDDING_MIN_INTERVAL_SECONDS`, `WORKER_EMBEDDING_MAX_RETRIES`, `WORKER_EMBEDDING_BACKOFF_BASE_SECONDS` 환경 변수로 조정한다. Chat 질의의 단일 embedding 요청에는 이 Worker 대기 정책을 적용하지 않는다.

## Object Storage와 CLOVA Speech 연결

Worker에 `NCP_OBJECT_STORAGE_ENDPOINT`, `NCP_OBJECT_STORAGE_BUCKET`, `NCP_OBJECT_STORAGE_ACCESS_KEY`, `NCP_OBJECT_STORAGE_SECRET_KEY`, `CLOVA_SPEECH_INVOKE_URL`, `CLOVA_SPEECH_API_KEY`를 모두 주입하면, 자막이 없는 선택 영상도 처리한다. Worker는 M4A 오디오를 `OBJECT_STORAGE_STT_INPUT_PREFIX` 아래에 저장하고, CLOVA Speech 장문 인식의 `/recognizer/object-storage`를 동기 호출한다. 원본 오디오, CLOVA Speech 원본 JSON, 정규화한 자막 JSON을 private Object Storage에 저장한 뒤 기존 chunk·embedding·pgvector 적재 경로를 재사용한다.

Speech Domain의 **인식 대상 저장 경로**는 `OBJECT_STORAGE_STT_INPUT_PREFIX`와 같아야 한다. 예를 들어 `clova-speech/input`을 선택했다면 Worker가 업로드한 `clova-speech/input/videos/...` 파일은 Speech 요청에서 상대 경로 `/videos/...`로 전달된다. 자막이 있는 영상도 원본 VTT와 정규화 JSON을 Object Storage에 저장한다. Object Storage 인증값이 없으면 기존 자막 분석은 계속 가능하지만, 자막 없는 영상은 명확한 설정 오류로 실패 처리한다.
