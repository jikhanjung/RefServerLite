# Zotero Sync 웹서버 응답성 개선

## 날짜: 2025-07-24

## 문제 현상
- Zotero 동기화 중 웹서버가 응답하지 않음
- CPU 사용률은 높지 않지만 웹 요청이 블로킹됨
- 사용자가 다른 페이지에 접근할 수 없음

## 문제 원인 분석

### 1. SQLite Database Lock 문제
- 각 Zotero 아이템마다 개별 `save()` 호출
- 개별 트랜잭션으로 인한 잦은 데이터베이스 락
- SQLite의 동시성 제한으로 웹 요청 블로킹

### 2. Event Loop 블로킹
- `await asyncio.sleep()` 호출이 있었지만 불충분
- 데이터베이스 I/O가 동기식으로 실행됨
- 배치 크기가 너무 커서 이벤트 루프 독점

### 3. 트랜잭션 세분화 부족
- 개별 save() 대신 bulk 연산 필요
- 원자적 연산 그룹화 부족

## 해결방안 구현

### 1. 배치 크기 최적화
```python
# 변경 전
batch_size = 20  # 너무 큰 배치 크기

# 변경 후  
batch_size = 5   # 작은 배치로 더 자주 yield
```

### 2. 이벤트 루프 양보 최적화
```python
# 변경 전
if processed_count % 2 == 0:
    await asyncio.sleep(0.2)  # 200ms

# 변경 후
await asyncio.sleep(0.05)  # 각 아이템 후 50ms yield
await asyncio.sleep(3.0)   # 배치 간 3초 대기
```

### 3. 데이터베이스 트랜잭션 최적화
```python
# 변경 전
zotero_item.save()

# 변경 후
with db.atomic():
    zotero_item.save()
    await asyncio.sleep(0.01)  # 트랜잭션 내에서도 yield
```

### 4. 컬렉션 동기화 배치 처리
```python
# 컬렉션도 배치로 처리
batch_size = 10
for i in range(0, len(collections), batch_size):
    batch = collections[i:i + batch_size]
    # 배치 처리 후 yield
    if i + batch_size < len(collections):
        await asyncio.sleep(0.1)
```

## 구체적 변경사항

### 1. `process_zotero_sync_job()` 함수
- 배치 크기: 20 → 5
- 아이템당 yield: 50ms 추가
- 배치간 대기: 1초 → 3초
- 진행률 업데이트: 매 배치마다

### 2. `process_zotero_item()` 함수
- 데이터베이스 저장 시 atomic 트랜잭션 적용
- 트랜잭션 내에서도 10ms yield

### 3. `sync_zotero_collections()` 함수
- 컬렉션을 10개씩 배치 처리
- 배치간 100ms yield 추가

## 성능 vs 응답성 트레이드오프

### 성능 영향
- 동기화 시간 약간 증가 (더 많은 대기시간)
- 네트워크 효율성은 유지 (배치 크기는 여전히 적정)

### 응답성 개선  
- 웹서버가 동기화 중에도 응답 가능
- 사용자가 다른 페이지 접근 가능
- 더 나은 멀티태스킹 경험

## 추가 고려사항

### 1. 모니터링
- 동기화 진행률을 더 자주 업데이트
- 웹 응답 시간 모니터링 필요

### 2. 향후 개선 가능 영역
- SQLite → PostgreSQL 고려 (더 나은 동시성)
- 별도 워커 프로세스로 동기화 분리
- 웹소켓 기반 실시간 진행률 표시

### 3. 설정 가능한 매개변수
- 배치 크기를 환경변수로 설정 가능하게 변경
- 대기 시간을 사용자 설정으로 조정 가능

## 결과
- 동기화 중에도 웹서버 정상 응답
- 사용자 경험 대폭 개선
- 동기화 안정성 유지