# Kakao 가져오기 운영 및 부하 확인

이 문서는 KakaoTalk 내보내기 파일을 `POST /folders/{folder_id}/imports/kakao`로 가져오는 작업의 로컬·NKS 운영 확인 절차다. 부하 테스트는 테스트 전용 workspace와 `analyze=false`를 기본값으로 사용한다. 실제 YouTube 분석은 외부 호출과 embedding 비용을 발생시킬 수 있으므로 승인된 비운영 환경에서만 `analyze=true`로 바꾼다.

## 합성 내보내기 파일과 반복 요청

아래는 URL 5,000개(그중 약 1,000개 중복)를 가진 KakaoTalk 형태의 UTF-8 텍스트 파일을 만든다. 각 YouTube ID는 합성 값이므로 실제 영상을 가리키지 않는다.

```bash
python3 scripts/load/generate_kakao_export.py \
  --output /tmp/kakao-youtube-load.txt --links 5000 --duplicate-rate 0.20
```

가져오기 API는 multipart 필드 `file`, 폼 필드 `analyze`, `priority`를 받는다. 다음 스크립트는 세션 cookie jar를 먼저 만들고, 동일 workspace의 `FOLDER_ID`에 요청을 반복한다. 결과별 JSON은 `/tmp/video-rag-kakao-import-results/`에 저장한다.

```bash
FOLDER_ID=<TEST_FOLDER_ID> REQUESTS=20 CONCURRENCY=1 \
  scripts/load/post_kakao_imports.sh
```

원격 테스트 환경은 다음처럼 명시한다. `CONCURRENCY>1`은 동일 cookie jar를 읽기만 하며, 처음 세션 생성은 단일 요청으로 끝낸다.

```bash
BASE_URL=https://api.staging.example.com FOLDER_ID=<TEST_FOLDER_ID> \
IMPORT_FILE=/tmp/kakao-youtube-load.txt REQUESTS=100 CONCURRENCY=5 \
ANALYZE=false PRIORITY=bulk COOKIE_JAR=/tmp/staging-video-rag.cookies \
scripts/load/post_kakao_imports.sh
```

API 계약은 다음과 같다.

```http
POST /folders/{folder_id}/imports/kakao
Content-Type: multipart/form-data

file=<KakaoTalk export .txt>
analyze=false|true
priority=bulk|normal|manual|ultra
```

성공 응답은 `202 Accepted`이며, `batch_id`, `total_urls`, `unique_videos`, `duplicates`, `queued_jobs`, `items[]`를 반환한다. `analyze=false`는 영상 목록만 만든다. `analyze=true`는 `jobs`에 durable row를 만들고, RabbitMQ가 켜져 있으면 같은 job id를 priority queue로 publish한다.

각 성공 응답에서 `batch_id`, `total_urls`, `unique_videos`, `duplicates`, `queued_jobs`를 보관한다. 예상과 다른 중복 수는 parser 정규화 또는 DB idempotency 문제를 구분할 근거가 된다. 테스트 후에는 생성한 test workspace 또는 batch 데이터를 별도 절차로 삭제한다. 운영 사용자 workspace에 테스트 파일을 올리지 않는다.

## 로컬 Docker 관찰

현재 Compose 구성의 앱 로그는 컨테이너 stdout/stderr를 통해 확인한다. API의 import 요청, Worker의 publish/consume 실패, 예외 stack trace를 같은 시간 범위에서 대조한다.

```bash
docker compose logs --since 15m --timestamps api worker
docker compose logs -f --timestamps api worker
docker compose ps
```

애플리케이션 로그는 JSON 한 줄 형태의 structured log를 목표로 한다. 최소 필드는 `timestamp`, `level`, `service`, `request_id`, `workspace_id`(비식별 ID), `folder_id`, `batch_id`, `job_id`, `event`, `duration_ms`, `error_type`다. 파일 내용, 세션 cookie, API key, DB URL, 원본 Kakao 메시지는 로그에 남기지 않는다. `batch_id`를 API와 Worker 로그에 공통으로 기록해야 하나의 업로드에서 publish·consume·DB 결과를 추적할 수 있다.

RabbitMQ가 로컬 Compose에 포함된 배포에서는 management UI 또는 CLI로 ready/unacked 수와 consumer 수를 확인한다. 아래 queue 이름은 배포의 실제 이름으로 교체한다.

```bash
docker compose exec rabbitmq rabbitmqctl list_queues name messages_ready messages_unacknowledged consumers
docker compose exec rabbitmq rabbitmqctl list_connections name state channels
```

`messages_ready`가 계속 증가하면 consumer 처리량보다 publish 속도가 크다는 뜻이고, `messages_unacknowledged`가 장시간 남으면 worker 중단·긴 작업·ack 실패를 조사한다. DLQ가 구성돼 있다면 해당 queue도 함께 관찰한다.

PostgreSQL의 batch/job 상태는 application schema와 실제 컬럼명을 확인한 뒤 조회한다.

```sql
SELECT status, count(*)
FROM import_batches
GROUP BY status
ORDER BY status;

SELECT status, count(*), min(created_at) AS oldest_created_at
FROM jobs
GROUP BY status
ORDER BY status;

SELECT import_batches.id AS batch_id,
       import_items.status,
       count(*) AS item_count,
       count(import_items.job_id) AS job_count
FROM import_batches
JOIN import_items ON import_items.batch_id = import_batches.id
WHERE import_batches.created_at >= now() - interval '15 minutes'
GROUP BY import_batches.id, import_items.status
ORDER BY import_batches.id, import_items.status;

SELECT status, count(*)
FROM outbox_events
GROUP BY status
ORDER BY status;
```

Redis를 rate limit 또는 idempotency에 사용하는 배포에서는 URL을 노출하지 않는 운영 shell에서 연결 상태와 key 수를 확인한다. key prefix는 실제 구성값으로 교체한다.

```bash
redis-cli -u "$REDIS_URL" PING
redis-cli -u "$REDIS_URL" --scan --pattern 'rate-limit:*' | head -100
redis-cli -u "$REDIS_URL" INFO stats
```

키 자체에는 사용자 식별자나 원문 URL을 넣지 않고, 필요하면 hash 또는 batch ID를 사용한다. rate-limit 거절(`429`) 수, Redis timeout, 중복 억제 hit 수를 앱 structured log와 지표로 집계한다.

## NKS/NCP 관찰

NKS에서는 namespace와 label을 실제 배포값으로 바꿔 API/consumer 로그와 pod 재시작을 확인한다.

```bash
kubectl -n <NAMESPACE> get pods -l app.kubernetes.io/part-of=video-rag
kubectl -n <NAMESPACE> logs deploy/<API_DEPLOYMENT> --since=15m --timestamps
kubectl -n <NAMESPACE> logs deploy/<WORKER_DEPLOYMENT> --since=15m --timestamps
kubectl -n <NAMESPACE> get events --sort-by=.lastTimestamp
kubectl -n <NAMESPACE> top pods
```

여러 replica의 순서를 함께 보려면 `kubectl logs -l app.kubernetes.io/component=worker --prefix --since=15m`를 사용한다. 일회성 `kubectl logs`는 pod 교체 후 기록을 잃으므로, production은 container stdout을 Kubernetes log collection으로 수집해 NCP Cloud Log Analytics로 전송한다. 수집 설정에서 namespace, workload, container 이름을 label로 보존하고 JSON 필드를 파싱한다. Cloud Log Analytics에서 다음 조건으로 대시보드/알림을 만든다.

- `event=import_received` 대비 `event=import_completed` 또는 `event=import_failed` 비율과 p95 `duration_ms`
- `event=queue_publish_failed`, `event=queue_consume_failed`, `error_type`별 오류 수
- RabbitMQ `messages_ready`, `messages_unacknowledged`, consumer 수, DLQ 누적량
- batch/job의 `queued` 체류 시간, `failed` 비율, worker pod restart 및 CPU/메모리
- Redis `429` 거절 수, timeout 수, rate-limit/idempotency hit 수

NKS 배포에서 추가해야 하는 환경 변수는 다음이다. 민감 값은 Kubernetes Secret으로 관리한다.

```text
ANALYSIS_QUEUE_PROVIDER=rabbitmq
WORKER_QUEUE_MODE=rabbitmq
WORKER_PREFETCH_COUNT=1
RABBITMQ_URL=amqp://<user>:<password>@<rabbitmq-host>:5672/%2F
REDIS_URL=redis://<redis-host>:6379/0
REDIS_IMPORT_RATE_LIMIT=30
REDIS_RATE_LIMIT_WINDOW_SECONDS=60
REDIS_LOCK_TTL_SECONDS=300
OBJECT_STORAGE_IMPORT_PREFIX=imports
```

운영 DB에는 `docs/db/2026-08-13-kakao-import-rabbitmq.sql`를 먼저 적용한다. 앱 시작 시 `initialize()`도 같은 schema를 보강하지만, 운영에서는 배포 전에 SQL을 적용하고 `idx_jobs_status_priority`, `uniq_jobs_active_idempotency`, `import_batches`, `import_items`, `outbox_events` 존재를 확인한다.

최소 상태 확인 API:

```bash
curl -fsS "$BASE_URL/ops/queue"
```

이 응답은 DB에 저장된 `jobs`, `import_batches`, `outbox_events`의 status별 count만 반환한다. 외부 공개 대시보드가 아니라 배포 직후 smoke check와 부하 테스트 전후 비교용이다.

알림 기준은 초기에는 정상 부하 테스트의 baseline을 측정한 뒤 정한다. 예: queue ready 수가 10분 동안 감소하지 않음, oldest queued job이 목표 처리시간을 초과함, DLQ가 0보다 큼, API/worker 오류율이 baseline을 지속 초과함. 알림을 받으면 `batch_id`로 API→RabbitMQ→Worker→PostgreSQL 로그를 추적하고, 우선 새 bulk import를 멈춘 뒤 consumer 상태·DB 연결·Redis 상태를 확인한다.

## 실행 전후 체크

1. staging/test `FOLDER_ID`, `BASE_URL`, `ANALYZE=false`, `PRIORITY=bulk`인지 확인한다.
2. import 전 queue depth, consumer 수, DB queued/running/failed 수, Redis ping 결과를 기록한다.
3. 요청 중 HTTP 상태와 각 response JSON의 `batch_id`를 보관한다.
4. 요청 후 queue depth가 내려가고, batch/job이 terminal 상태가 되는지 확인한다.
5. 오류가 있으면 response와 API/Worker structured log를 `batch_id` 기준으로 함께 보관한다. 재시도 전에 idempotency/duplicate 집계가 기대와 일치하는지 확인한다.
