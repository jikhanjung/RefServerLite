# Zotero 가져오기 데이터베이스 잠금 문제 분석

## 문제 개요

2025년 1월 17일 Zotero 가져오기 스크립트 실행 중 SQLite 데이터베이스 잠금 오류가 반복적으로 발생하여 대부분의 업로드가 실패하는 문제가 확인되었습니다.

## 오류 로그 분석

### 주요 오류 메시지
```
Upload failed: {"detail":"Database error: database is locked"}
500 Server Error: Internal Server Error for url: http://localhost:8000/api/v1/papers/upload_with_metadata
```

### 발생 패턴
- **Zotero PDF 다운로드**: 정상 작동 (모든 요청 성공)
- **RefServerLite 업로드**: 대부분 실패 (8건 중 1건만 성공)
- **실패 시점**: 업로드 시도 후 약 5초 뒤 일관되게 발생
- **성공 사례**: "The contribution of glacial erosion to shaping the hidden landscape of East Antarctica" 1건만 성공

### 처리된 항목들
```
✗ Failed: The Geology of Antarctica
✗ Failed: Marine Ice Sheet Collapse Potentially Under Way for the Thwaites Glacier Basin, West Antarctica
✓ Success: The contribution of glacial erosion to shaping the hidden landscape of East Antarctica
✗ Failed: A new global ice sheet reconstruction for the past 80 000 years
✗ Failed: The geology of Buckley and Darwin Nunataks, Beardmore Glacier, Ross Dependency, Antarctica
✗ Failed: The geology of the Mt Markham region, Ross dependency, Antarctica
✗ Failed: Archaeocyathine Limestones of Antarctica
```

## 원인 분석

### 1. SQLite 동시성 제한
- SQLite는 기본적으로 단일 writer만 지원
- 여러 프로세스/스레드가 동시에 쓰기 작업을 시도할 때 잠금 발생

### 2. 백그라운드 프로세싱과의 충돌
RefServerLite의 백그라운드 파이프라인과 API 요청 간 리소스 경합:
- OCR 처리 중인 문서
- 메타데이터 추출 작업
- 임베딩 생성 프로세스
- 시맨틱 청킹 작업

### 3. 트랜잭션 관리 문제
```python
# 문제가 될 수 있는 시나리오
# 1. 파일 업로드 중 예외 발생
# 2. 트랜잭션이 제대로 롤백되지 않음
# 3. DB 연결이 잠긴 상태로 남아있음
```

### 4. API 엔드포인트의 긴 처리 시간
새로운 `/api/v1/papers/upload_with_metadata` 엔드포인트에서:
1. Paper 레코드 생성
2. Metadata 레코드 생성 (source='user_api')
3. ZoteroLink 레코드 생성 (선택적)
4. ProcessingJob 레코드 생성
5. 백그라운드 프로세싱 시작

각 단계에서 DB 잠금이 발생할 수 있음.

## 해결 방안

### 1. 즉시 적용 가능한 해결책

#### A. 재시도 로직 구현
```python
# scripts/import_from_zotero.py 수정
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=4, max=30)
)
def upload_to_refserver(self, item, pdf_content, attachment_filename):
    # 기존 업로드 로직
    pass
```

#### B. 배치 처리 설정 조정
```yaml
# config.yml 수정
import_options:
  batch_size: 1           # 동시 처리 수 줄이기
  delay_seconds: 15       # 요청 간 지연 시간 증가
```

#### C. 서버 재시작 후 재시도
```bash
docker-compose restart
# 백그라운드 작업 완료 대기 후 가져오기 재시도
```

### 2. 백엔드 개선 방안

#### A. SQLite WAL 모드 활성화
```python
# app/models.py에서 DB 초기화 시
def init_database(database_path: str):
    db.init(database_path)
    # WAL 모드 활성화로 동시성 개선
    db.execute_sql('PRAGMA journal_mode=WAL;')
    db.execute_sql('PRAGMA synchronous=NORMAL;')
    db.execute_sql('PRAGMA cache_size=1000;')
    db.execute_sql('PRAGMA temp_store=memory;')
```

#### B. 트랜잭션 관리 개선
```python
# app/main.py의 upload_with_metadata 엔드포인트 수정
@app.post("/api/v1/papers/upload_with_metadata")
async def upload_with_metadata(...):
    with db.atomic() as transaction:  # 명시적 트랜잭션 관리
        try:
            # 모든 DB 작업을 하나의 트랜잭션으로
            paper = Paper.create(...)
            metadata = Metadata.create(...)
            if zotero_key:
                zotero_link = ZoteroLink.create(...)
            job = ProcessingJob.create(...)
        except Exception as e:
            transaction.rollback()
            raise
```

#### C. 연결 풀 관리
```python
# app/models.py
from playhouse.pool import PooledSqliteDatabase

# 기존 SqliteDatabase 대신 PooledSqliteDatabase 사용
db = PooledSqliteDatabase(
    None,
    max_connections=10,
    stale_timeout=300,  # 5분 후 연결 해제
    timeout=30          # 30초 대기
)
```

### 3. 아키텍처 개선 방안

#### A. 비동기 업로드 구현
```python
# 파일 업로드와 프로세싱을 분리
@app.post("/api/v1/papers/upload_with_metadata")
async def upload_with_metadata(...):
    # 1. 최소한의 DB 작업만 수행 (Paper, Metadata만)
    # 2. ProcessingJob은 별도 큐에 추가
    # 3. 백그라운드에서 순차적으로 처리
```

#### B. Redis 큐 도입 고려
```python
# 대량 가져오기 시 Redis나 Celery 사용
# DB 경합을 줄이고 안정적인 백그라운드 처리
```

## 임시 운영 가이드

### 현재 상황에서의 가져오기 방법

1. **단일 항목 테스트**
   ```bash
   python import_from_zotero.py --limit 1 --dry-run  # 먼저 확인
   python import_from_zotero.py --limit 1            # 실제 가져오기
   ```

2. **소량 배치로 나누어 처리**
   ```bash
   # 5개씩 나누어 처리, 각 배치 간 충분한 대기
   python import_from_zotero.py --limit 5
   # 성공 확인 후 다음 배치
   ```

3. **서버 상태 모니터링**
   ```bash
   # 백그라운드 작업 완료 상태 확인
   curl http://localhost:8000/api/v1/admin/status
   ```

## 향후 개선 계획

1. **단기 (1주일 내)**
   - 재시도 로직 구현
   - WAL 모드 활성화
   - 트랜잭션 관리 개선

2. **중기 (1개월 내)**
   - PooledSqliteDatabase 도입
   - 비동기 처리 아키텍처 구현

3. **장기 (분기별)**
   - PostgreSQL 마이그레이션 고려
   - 마이크로서비스 아키텍처 검토

## 결론

현재 문제는 SQLite의 동시성 제한과 백그라운드 프로세싱 간의 리소스 경합으로 판단됩니다. 단기적으로는 재시도 로직과 배치 크기 조정으로 해결하고, 중장기적으로는 DB 아키텍처와 트랜잭션 관리 개선이 필요합니다.