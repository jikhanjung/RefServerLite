# Event Loop 블로킹 문제 분석 및 해결방안

## 날짜: 2025-07-24

## 문제 현상
- Zotero 동기화 중 웹서버가 아예 HTTP 요청을 받지 못함
- 웹서버 로그에 요청 기록조차 남지 않음
- CPU 사용률은 높지 않지만 완전히 응답 불가 상태

## 문제 원인 분석

### 예상했던 원인 vs 실제 원인

#### 예상: DB Lock 문제
```
HTTP 요청 → FastAPI → DB 접근 → SQLite Lock → 대기
```
- **예상**: DB 락으로 인한 요청 지연
- **현상**: HTTP 요청조차 로그에 안 찍힘 → DB 락이 아님

#### 실제: Event Loop 완전 블로킹
```
asyncio.create_task(sync_job) → zot.everything() → 동기식 네트워크 I/O → Event Loop 블로킹
```

### Event Loop 블로킹의 메커니즘

#### FastAPI/ASGI 아키텍처
```python
# 단일 이벤트 루프에서 모든 요청 처리
async def handle_request_1():
    return {"result": "ok"}  # 빠른 응답

async def handle_request_2():  
    items = zot.everything(zot.items())  # 동기식 블로킹!
    return {"result": "ok"}

# 모든 요청이 같은 이벤트 루프에서 대기
```

#### 블로킹 발생 지점
1. **Zotero API 호출**:
   ```python
   # 이 호출들이 완전히 동기식
   collections = zot.everything(zot.collections())  # 네트워크 I/O 블로킹
   items = zot.everything(zot.items())              # 네트워크 I/O 블로킹
   ```

2. **Event Loop 독점**:
   - `await` 없는 동기식 네트워크 호출
   - 다른 모든 async 태스크(HTTP 요청 포함) 대기
   - 백그라운드 태스크도 같은 이벤트 루프 사용

## 프레임워크별 비교

### Django (WSGI) 접근법
```python
# Django view - 멀티스레드/멀티프로세스
def sync_zotero(request):
    items = zot.everything(zot.items())  # 동기식 호출
    # 이 요청만 블로킹, 다른 요청들은 별도 워커에서 정상 처리
    return JsonResponse({"status": "ok"})

# 아키텍처
nginx → gunicorn(4 workers) → Django
요청1 → Worker1 (블로킹 중)
요청2 → Worker2 (정상 처리) ✅
요청3 → Worker3 (정상 처리) ✅
```

**Django의 장점**:
- 자연스러운 동기식 라이브러리 사용
- 워커 격리로 블로킹 영향 최소화
- Celery 등 백그라운드 작업 도구 성숙

### FastAPI (ASGI) 접근법  
```python
# FastAPI - 단일 이벤트 루프
async def sync_zotero():
    items = zot.everything(zot.items())  # 전체 서버 블로킹! ❌
    return {"status": "ok"}

# 아키텍처
nginx → uvicorn(1 event loop) → FastAPI
모든 요청 → Event Loop (하나가 블로킹되면 전체 멈춤)
```

**FastAPI의 특징**:
- 고성능 비동기 처리
- 단일 이벤트 루프로 메모리 효율적
- 동기식 블로킹에 취약

## 해결방안

### 1. Thread Pool Executor 사용
```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

async def sync_zotero_items(zot_instance):
    # 동기식 Zotero API를 별도 스레드에서 실행
    items = await asyncio.get_event_loop().run_in_executor(
        None,  # Default ThreadPoolExecutor
        lambda: zot_instance.everything(zot_instance.items())
    )
    return items

async def sync_zotero_collections(zot_instance):
    collections = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: zot_instance.everything(zot_instance.collections())
    )
    return collections
```

### 2. 멀티프로세싱 (대안)
```python
import multiprocessing as mp

def zotero_sync_worker(user_id, api_key):
    # 완전히 별도 프로세스에서 실행
    zot = zotero.Zotero(library_id, 'user', api_key)
    items = zot.everything(zot.items())
    # 결과를 DB에 저장하고 완료 신호
```

### 3. Django로 마이그레이션 (장기적)
- 동기식 라이브러리와 자연스럽게 호환
- 멀티워커 아키텍처로 안정성 확보
- Celery 등 백그라운드 작업 도구 활용

## 성능 vs 안정성 트레이드오프

### FastAPI + Thread Pool
**장점**:
- 높은 동시성 (비동기 I/O)
- 메모리 효율성
- 현재 코드베이스 유지

**단점**:  
- 동기식 코드 처리 복잡성
- Thread Pool 오버헤드
- 디버깅 복잡성 증가

### Django + 멀티워커
**장점**:
- 동기식 라이브러리 자연스럽게 사용
- 워커 격리로 안정성 확보
- 간단한 개발 및 디버깅

**단점**:
- 메모리 사용량 증가 (워커당 프로세스)
- 동시성 제한 (워커 수에 의존)

## 구현 계획

### Phase 1: Thread Pool 적용
1. Zotero API 호출을 Thread Pool로 래핑
2. 기존 비동기 구조 유지
3. 웹서버 응답성 확보

### Phase 2: 성능 최적화
1. Thread Pool 크기 조정
2. 메모리 사용량 모니터링
3. 동시성 제한 설정

### Phase 3: 장기 검토
1. Django 마이그레이션 검토
2. 마이크로서비스 분리 고려
3. 전용 백그라운드 워커 도입

## 결론

현재 문제는 **동기식 네트워크 I/O가 단일 이벤트 루프를 블로킹**시키는 것입니다. Thread Pool을 사용하여 동기식 작업을 별도 스레드로 분리하면 웹서버 응답성을 확보할 수 있습니다.

Django로의 마이그레이션도 좋은 장기적 대안이지만, 단기적으로는 Thread Pool 적용으로 문제를 해결할 수 있습니다.