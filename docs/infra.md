# Video RAG MVP 운영 인프라

> 시각 자료는 [infra.html](infra.html)에서 확인한다. 이 문서는 현재 로컬 구현과 NCP 운영 목표를 구분해, 무엇을 지금 만들고 무엇을 보류할지 기록한다.

## 결론

이 서비스는 MSA로 분리하지 않는다. **같은 FastAPI 코드베이스와 같은 Docker 이미지**를 API와 Worker라는 두 실행 역할로만 나눈다.

| 역할 | 시작 명령 | 책임 | 외부 공개 |
| --- | --- | --- | --- |
| API | `uvicorn app.main:app` | 로그인/작업공간, 채널·영상 등록, 작업 등록, 메타데이터·RAG 검색, Chat 응답 | Load Balancer를 통한 HTTPS만 |
| Worker | `python -m app.worker` | 채널 스캔, `yt-dlp`, 자막/STT, 청킹, embedding, 파일 저장 | 없음 |

메타데이터 검색은 API가 PostgreSQL을 읽어 바로 반환하는 기능이다. 별도 검색 서버를 만들지 않는다. 분석 대기열이 길면 API가 아니라 Worker를 먼저 늘린다.

## 현재 구현과 NCP 운영 목표

| 항목 | 현재 로컬 | NCP 운영 목표 |
| --- | --- | --- |
| API | FastAPI `app/main.py` | 같은 코드의 API 서버 1대에서 시작, 필요 시 다중화 |
| Worker | `app/worker.py` 단일 프로세스 | 동일 이미지의 Worker를 독립적으로 증설 |
| 작업 큐 | SQLite `jobs` 테이블 | Cloud DB for PostgreSQL `jobs` + `FOR UPDATE SKIP LOCKED` |
| RAG 벡터 | SQLite JSON 문자열 | PostgreSQL + `pgvector` |
| 파일 | `data/downloads/` | private Object Storage, DB에는 object key만 저장 |
| AI | mock 또는 CLOVA Studio | CLOVA Studio, 필요 시 CLOVA Speech |

현재 `app/worker.py`의 `claim_job()`은 SQLite에서 단일 Worker가 작업을 가져오는 로컬 구현이다. 이 문서의 PostgreSQL 큐, Object Storage 업로드, CLOVA Speech 장문 인식은 **운영 목표**이며 아직 코드에 적용되지 않았다.

## 전체 구조

~~~mermaid
flowchart LR
    U[사용자 브라우저] --> LB[Load Balancer]
    subgraph VPC[NCP VPC]
      subgraph Public[Public Subnet]
        LB
      end
      subgraph App[Private App Subnet]
        API[FastAPI API]
        W[Analysis Worker]
        SCH[채널 스케줄러<br/>Worker cron]
      end
      subgraph Data[Private Data Subnet]
        DB[(Cloud DB for PostgreSQL<br/>서비스 DB · jobs · pgvector)]
      end
      NAT[NAT Gateway]
      API --> DB
      API --> NAT
      SCH --> DB
      W --> DB
      W --> NAT
    end
    NAT --> YT[YouTube]
    NAT --> STUDIO[CLOVA Studio<br/>Embedding · Chat]
    NAT --> SPEECH[CLOVA Speech<br/>자막 없을 때 STT]
    W --> OS[Object Storage<br/>private bucket]
    LOG[Cloud Log Analytics / Insight] -. 관찰 .-> API
    LOG -. 관찰 .-> W
    LOG -. 관찰 .-> DB
~~~

### 네트워크 원칙

- 공개 인바운드는 `사용자 → Load Balancer → API` 하나다. Worker와 PostgreSQL에는 public IP나 공개 포트를 열지 않는다.
- 채널 스케줄러는 Private App subnet의 Worker cron으로 실행한다. public IP·공개 endpoint·Load Balancer 경로 없이 PostgreSQL `jobs`에만 `scan_channel` 작업을 등록한다.
- API와 Worker만 PostgreSQL ACG 접근을 허용한다.
- API와 Worker가 YouTube·CLOVA API를 호출할 때만 NAT Gateway를 통한 outbound 통신을 허용한다.
- Object Storage 버킷은 private으로 유지한다. 원본 VTT·오디오·STT 결과는 Object Storage에, 검색용 청크와 embedding은 PostgreSQL에 둔다.
- API key, DB 비밀번호, Object Storage 접근 키는 이미지·Git·브라우저 JavaScript에 넣지 않고 서버 런타임 환경 변수 또는 비밀 저장소로 주입한다.

## 세 가지 서비스 흐름은 서로 다르다

같은 PostgreSQL을 쓰더라도 시작 조건이 다르다. **채널 스캔은 영상 목록만 갱신**하고, **사용자가 분석을 누른 영상만 RAG 문서로 만든다.**

### 1. 채널 목록 갱신: 스케줄러가 작업을 만들고, Worker가 가져간다

~~~mermaid
flowchart LR
    S[채널 스케줄러] -->|INSERT queued| J[(PostgreSQL jobs<br/>scan_channel)]
    J <-->|poll queued · claim running| W[Analysis Worker]
    W --> Y[YouTube]
    Y --> V[(videos 테이블<br/>제목 · 설명 · 업로드일)]
~~~

- 초기에는 Private App subnet의 Worker 서버 cron이 `scan_channel` 작업을 등록한다. 별도 스케줄러 서버는 필요 없다.
- 스케줄이 많아져 분리하더라도 private app subnet 안의 경량 scheduler 역할로 분리한다. public endpoint나 스케줄러 전용 Load Balancer는 만들지 않는다.
- Worker는 `yt-dlp --flat-playlist --dump-json --skip-download`로 영상 목록과 간단 메타데이터만 수집한다.
- 이 단계에서는 자막 다운로드, 오디오 저장, STT, embedding, RAG 문서 생성을 하지 않는다.

### 2. 선택 영상 분석: 사용자 → `analyze_video`, 이후 Worker가 claim

~~~mermaid
flowchart LR
    B[사용자: 분석하기] --> A[FastAPI API]
    A -->|INSERT queued| J[(PostgreSQL jobs<br/>analyze_video)]
    J <-->|poll queued · claim running| W[Analysis Worker]
    W --> Y[YouTube 자막 수집]
    Y --> C{자막 있음?}
    C -->|예| T[자막 구간 정규화]
    C -->|아니오| S[Object Storage 오디오]
    S --> P[CLOVA Speech STT]
    P -->|STT text 반환| T
    T -->|embedding 요청| E[CLOVA Studio Embedding]
    E -->|vector 반환| W2[같은 Worker<br/>원문 · 시간 · vector 저장]
    W2 --> R[(transcript_chunks + pgvector)]
~~~

- `POST /videos/{id}/analyze`는 jobs에 `analyze_video`를 저장하고 `202 { job_id, status: queued }`를 즉시 반환한다.
- Worker는 DB가 보내 준 작업을 받는 것이 아니라, `queued` 작업을 polling해 `FOR UPDATE SKIP LOCKED`로 선점한다. 상태를 `running`으로 바꾼 뒤 `yt-dlp`로 자막을 수집한다. 자막이 없을 때만 오디오를 저장하고 CLOVA Speech STT를 대체 경로로 호출한다.
- 정규화된 자막 구간은 시간 정보와 함께 CLOVA Studio Embedding으로 vector를 만들고, 원문·시간·vector를 PostgreSQL에 저장한다.
- 스케줄러는 `analyze_video` 작업을 만들지 않는다. 사용자가 선택한 영상만 이 흐름을 탄다.

### 3. RAG 질문: API → 검색 → CLOVA Studio Chat

~~~mermaid
flowchart LR
    B[사용자 질문] --> A[FastAPI API]
    A -->|질문 embedding 요청| E[CLOVA Studio Embedding]
    E -->|질문 vector 반환| A
    A -->|Top-K 검색| P[(pgvector)]
    P -->|원문 자막 · 시간 반환| A
    A -->|근거 + 질문| C[CLOVA Studio Chat]
    C -->|자연어 답변 반환| A
    A --> R[답변 + 실제 재생 시간 링크]
~~~

1. 브라우저가 `POST /chat`으로 질문을 보낸다.
2. API가 CLOVA Studio Embedding으로 질문 vector를 만들고, 현재 작업공간의 분석 완료 자막 구간만 `pgvector`에서 Top-K 검색한다.
3. API가 검색 결과의 **원문 자막과 시간**을 프롬프트 근거로 구성해 CLOVA Studio Chat에 전달한다. vector 숫자 자체를 Chat 모델에 보내는 것은 아니다.
4. Chat 모델이 자연어 답변을 만들고, API가 근거 구간의 실제 재생 시간 링크와 함께 반환한다.

이 흐름은 Worker를 거치지 않으며, CLOVA Speech도 사용하지 않는다. CLOVA Speech는 선택 영상에 자막이 없을 때 음성을 텍스트로 바꾸는 STT 서비스일 뿐 챗봇이 아니다.

### 분석 상태 SSE: Worker → DB 상태 갱신 → FastAPI → Browser

분석 진행 알림은 별도 Pub/Sub나 Worker의 HTTP callback으로 만들지 않는다. Worker는 기존 책임대로 `jobs`와 `videos`의 상태만 갱신하고, FastAPI가 DB를 1초 간격으로 읽어 SSE로 전달한다.

~~~mermaid
sequenceDiagram
    participant B as Browser EventSource
    participant A as FastAPI SSE endpoint
    participant W as Analysis Worker
    participant D as PostgreSQL jobs / videos

    B->>A: GET /videos/{id}/events (session cookie)
    A->>D: 영상 · 작업공간 소유권과 현재 상태 확인
    A-->>B: retry + 최초 analysis_status event
    W->>D: queued → running → embedding → succeeded 기록
    loop 1초 간격, 상태 변경 시에만
        A->>D: status / progress 조회
        D-->>A: 최신 job + video 상태
        A-->>B: analysis_status event
    end
    A-->>B: succeeded 또는 failed event 후 종료
~~~

- EventSource는 같은 origin의 기존 세션 쿠키를 사용한다. URL query string에 사용자 ID·작업공간 코드·비밀값을 넣지 않는다.
- SSE endpoint는 최초 연결과 매 조회마다 영상의 작업공간 소유권 범위에서 상태를 읽는다. 다른 작업공간의 같은 `video_id`는 구독할 수 없다.
- DB 상태가 바뀌지 않으면 event를 반복 전송하지 않으며, 약 20초마다 `: heartbeat` comment를 보낸다.
- NCP Load Balancer 또는 앞단 프록시에서는 SSE 응답 버퍼링 해제와 idle timeout이 heartbeat 간격보다 충분히 큰지 별도로 확인한다.

## PostgreSQL을 초기 메시지 큐로 사용하는 방식

초기 운영에는 Redis나 Kafka가 필수는 아니다. PostgreSQL의 `jobs` 테이블이 작업 상태와 대기열을 함께 보관한다.

~~~sql
CREATE TABLE jobs (
  id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  kind          TEXT NOT NULL CHECK (kind IN ('scan_channel', 'analyze_video')),
  resource_id   BIGINT NOT NULL,
  status        TEXT NOT NULL DEFAULT 'queued'
                CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
  attempts      INTEGER NOT NULL DEFAULT 0,
  max_attempts  INTEGER NOT NULL DEFAULT 3,
  available_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  locked_by     TEXT,
  locked_at     TIMESTAMPTZ,
  error_message TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  started_at    TIMESTAMPTZ,
  finished_at   TIMESTAMPTZ
);

CREATE INDEX idx_jobs_claim
  ON jobs (available_at, id)
  WHERE status = 'queued';
~~~

Worker는 다음 쿼리를 **짧은 트랜잭션**에서 실행해 한 작업만 선점한다. 상태를 `running`으로 바꾼 뒤 즉시 commit하고, 다운로드·STT·embedding은 트랜잭션 밖에서 실행한다.

~~~sql
WITH next_job AS (
  SELECT id
  FROM jobs
  WHERE status = 'queued'
    AND available_at <= now()
  ORDER BY created_at, id
  FOR UPDATE SKIP LOCKED
  LIMIT 1
)
UPDATE jobs AS j
SET status = 'running',
    attempts = j.attempts + 1,
    locked_by = $1,
    locked_at = now(),
    started_at = COALESCE(j.started_at, now())
FROM next_job
WHERE j.id = next_job.id
RETURNING j.*;
~~~

### 실패와 재시도

- `locked_at`이 오래된 `running` 작업은 Worker가 중단된 것으로 보고 회수한다.
- `attempts < max_attempts`이면 미래의 `available_at`으로 되돌려 재시도한다.
- 최대 재시도를 넘긴 작업은 `failed`와 원인을 기록한다.
- 동일 영상 분석의 중복 등록은 `resource_id`와 `status`를 확인하거나 별도 deduplication key/UNIQUE 제약으로 막는다.

## NCP 서비스 선택

| 시점 | 서비스 | 이 프로젝트에서의 책임 |
| --- | --- | --- |
| 지금 | VPC, Subnet, ACG | 공개 진입점과 private API/Worker/DB를 분리 |
| 지금 | Server | API 1대, Worker 1대부터 시작 |
| 지금 | Cloud DB for PostgreSQL | 서비스 데이터, `jobs`, `pgvector` |
| 지금 | Object Storage | VTT·오디오·STT 결과의 private 보관 |
| 지금 | CLOVA Studio | 분석·질문 embedding, 자막 근거 기반 Chat 답변 |
| 자막 없을 때 | CLOVA Speech | 선택 영상 오디오의 STT. 챗봇이나 RAG 질문에는 사용하지 않음 |
| 지금 | Cloud Log Analytics, Cloud Insight | 오류, 분석 적체, 처리 시간 관찰 |
| 필요 시 | Load Balancer, Auto Scaling | API 인스턴스가 2대 이상이거나 공개 요청이 늘 때 |
| 필요 시 | Cloud DB for Redis | PostgreSQL 큐로 우선순위·지연 재시도를 관리하기 어려울 때 Redis Streams 검토 |
| 보류 | Cloud Data Streaming Service | 다수 Consumer와 높은 이벤트 처리량이 필요한 Kafka 단계 |

Cloud DB for PostgreSQL은 관리형 PostgreSQL과 `pgvector` 확장을 제공하므로, 초기 RAG에서 별도 벡터 DB를 추가하지 않는다. Object Storage는 S3 호환 파일 보관소이며 VPC private domain 접근을 지원한다. Cloud Functions는 Korea 리전에서 cron·Object Storage trigger를 지원하지만, 현재 핵심 경로는 파일 업로드가 아니라 URL 기반 분석 요청이므로 Worker cron부터 시작한다.

- [Cloud DB for PostgreSQL: 확장 관리](https://guide.ncloud-docs.com/docs/en/clouddbforpostgresql-postgresqlextension)
- [Ncloud Storage: VPC 접근 방식](https://guide.ncloud-docs.com/release-20260423/docs/en/ncloudstorage-overview)
- [Cloud Functions: 지원 트리거](https://guide.ncloud-docs.com/docs/en/cloudfunctions-spec)
- [Cloud Data Streaming Service: 구성 개념](https://guide.ncloud-docs.com/docs/en/cdss-info)

## Load Balancer는 하나면 된다

초기 구성에서는 사용자 요청용 Application Load Balancer 하나와 FastAPI Target Group 하나만 둔다.

| 들어오는 경로 | Load Balancer 처리 | 도착 대상 |
| --- | --- | --- |
| `POST /chat` | HTTPS listener의 기본 규칙 | FastAPI API Target Group |
| `POST /videos/{id}/analyze` | HTTPS listener의 기본 규칙 | FastAPI API Target Group |
| `POST /channels/{id}/scan` | HTTPS listener의 기본 규칙 | FastAPI API Target Group |
| Private App subnet 채널 스케줄러의 주기 실행 | Load Balancer를 통과하지 않음 | PostgreSQL에 `scan_channel` 작업 등록 |

스케줄러는 외부 사용자의 HTTP 요청을 받는 서비스가 아니다. Private App subnet의 Worker cron이 내부 DB에 작업만 등록하므로, public IP·스케줄러 전용 Load Balancer·Target Group을 만들지 않는다.

NCP Application Load Balancer는 Host Header와 Path Pattern 조건으로 서로 다른 Target Group에 분기할 수 있다. 따라서 나중에 `api.example.com`과 별도 관리자 애플리케이션을 운영하거나, 완전히 다른 HTTP 서버를 추가하면 하나의 Load Balancer에서 도메인/경로별 분기를 검토할 수 있다. 그러나 현재는 모든 공개 endpoint가 같은 FastAPI 코드와 같은 API 서버로 향하므로 분기 규칙을 추가해도 얻는 이점이 없다. [Application Load Balancer 규칙](https://guide.ncloud-docs.com/docs/en/loadbalancer-application-vpc)

## 확장 기준

| 관찰한 신호 | 먼저 바꿀 것 | 아직 바꾸지 않을 것 |
| --- | --- | --- |
| `jobs.status='queued'`의 대기 시간이 길어짐 | Worker 2~3대를 추가 | API 증설 |
| API의 CPU·응답 시간이 높음 | API를 늘리고 Load Balancer 연결 | Worker만 무작정 추가 |
| 재시도, 우선순위, 지연 예약 요구가 복잡해짐 | Cloud DB for Redis + Redis Streams 검토 | 즉시 Kafka 도입 |
| 여러 팀/서비스가 독립적으로 이벤트를 소비 | Kafka 도입 검토 | PostgreSQL 큐에 모든 이벤트 유지 |

NCP Cloud Data Streaming Service는 Kafka 클러스터를 관리형으로 제공하지만, 클러스터가 매니저 노드 1대와 Broker 3대 이상으로 구성된다. 이 MVP의 영상 분석 대기열에는 과한 시작점이다. [Cloud Data Streaming Service 개념](https://guide.ncloud-docs.com/docs/cdss-info)

## 배포 순서

1. VPC와 public/private subnet, ACG를 만든다.
2. Cloud DB for PostgreSQL을 만들고 `pgvector`와 운영용 `jobs` 스키마를 적용한다.
3. Object Storage private bucket을 만들고 `raw/`, `captions/`, `audio/`, `stt/` prefix를 정한다.
4. 같은 Docker image를 Container Registry에 push한다.
5. private API 서버에는 `uvicorn app.main:app`, private Worker 서버에는 `python -m app.worker`를 실행한다.
6. API를 여러 대 운영할 때 Load Balancer target group에 API만 등록한다. Worker는 등록하지 않는다.
7. 분석 한 건이 `queued → running → succeeded` 또는 원인이 있는 `failed`로 끝나는지 확인한 뒤 Worker를 증설한다.

## 관련 코드

- [app/main.py](../app/main.py): 분석 작업을 등록하고 `202`를 반환하는 HTTP API
- [app/worker.py](../app/worker.py): 현재 로컬 Worker
- [app/db.py](../app/db.py): SQLite `jobs` 스키마와 로컬 상태 저장
- [docs/AI_SERVICES.md](AI_SERVICES.md): mock/CLOVA 전환과 STT의 현재 범위
