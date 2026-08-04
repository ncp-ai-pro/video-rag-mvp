# Video RAG MVP (local)

여러 YouTube 채널의 **메타데이터만** 먼저 수집하고, 사용자가 선택한 영상만 자막/음성 기반 RAG로 분석하는 FastAPI 프로토타입입니다.

첫 접속 시 익명 작업공간과 8자리 작업공간 코드가 자동 생성됩니다. 같은 브라우저는 세션 쿠키로 이어지며, 다른 브라우저에서는 화면 상단의 `기존 작업공간 연결`에 코드를 입력해 같은 데이터에 연결합니다.

## 현재 구현 범위

- `POST /channels/{id}/scan`: `yt-dlp --flat-playlist` 작업을 큐에 등록한다. 이 단계는 영상·오디오를 다운로드하지 않는다.
- `POST /recommendations`: 모든 영상의 제목·설명 embedding으로 메타데이터 추천을 반환한다.
- `POST /videos/{id}/analyze`: 선택한 영상만 자막 수집 작업을 큐에 등록한다.
- `POST /videos/{id}/transcript`: 로컬 테스트용 시간 구간 자막을 넣는다.
- `POST /chat`: 분석 완료된 자막 chunk만 검색하고, 답변과 최대 3개의 실제 재생 시간 링크를 반환한다.

로컬 큐는 SQLite `jobs` 테이블과 별도 Worker 프로세스로 구현했다. NCP 배포에서는 이 경계를 유지한 채 `jobs` 소비부를 Cloud DB for Redis 기반 큐로 바꾸고 SQLite를 Cloud DB for PostgreSQL + `pgvector`로 교체한다.

## 실행

Mac에서 다음을 실행한다.

```bash
cd /Users/kimgt/Developer/Project/ncp-ai/video-rag-mvp
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload
```

다른 터미널에서 Worker를 실행한다.

```bash
cd /Users/kimgt/Developer/Project/ncp-ai/video-rag-mvp
.venv/bin/python -m app.worker
```

## Docker Compose 배포

API와 Worker는 동일한 SQLite `jobs` 테이블과 `data/`를 공유해야 하므로, Compose는 두 컨테이너에 `video-rag-data` 영속 볼륨을 함께 연결한다. 현재 SQLite MVP에서는 Worker를 한 개만 실행한다.

서버 배포 전에는 `.env`를 Git에 올리지 않고 `.env.example`을 복사해 CLOVA 키와 배포 환경 값을 입력한다. `.env`가 없으면 mock 모드 기본값으로도 컨테이너를 띄울 수 있지만, 실제 NCP AI 호출에는 사용할 수 없다.

```bash
cp .env.example .env
docker compose up -d --build
docker compose ps
```

API는 `http://<SERVER_IP>:8000/health`에서 확인할 수 있다. Load Balancer로 HTTPS를 종료하는 운영 환경에서는 `.env`의 `SESSION_COOKIE_SECURE=true`로 바꾼다.

```bash
docker compose logs -f api
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

## 아직 NCP 연결이 필요한 항목

자막이 없는 영상의 CLOVA Speech 장문 인식과 Object Storage 업로드는 인증키·버킷·callback URL이 필요한 외부 연동이다. 현재 Worker는 자막 수집까지 실제로 실행하고, 자막이 없으면 `subtitle_not_found`로 작업을 실패 처리한다. 이 상태를 `jobs.error_message`와 `videos.analysis_error`에서 확인할 수 있다.
