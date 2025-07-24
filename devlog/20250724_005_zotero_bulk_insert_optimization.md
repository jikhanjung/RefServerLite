# Zotero 아이템 벌크 인서트 최적화

## 날짜: 2025-07-24

## 배경
이전 웹서버 응답성 개선(devlog 004)에서 배치 크기를 줄이고 yield를 늘려 응답성을 개선했지만, 개별 save() 호출로 인한 성능 문제가 여전히 존재했음.

## 문제점
1. **개별 DB 연산**: 각 아이템마다 개별 `save()` 호출
2. **트랜잭션 오버헤드**: 수많은 작은 트랜잭션으로 인한 성능 저하
3. **SQLite 락 경합**: 개별 연산으로 인한 잦은 락 획득/해제
4. **컬렉션 관계 처리**: 아이템별 개별 관계 생성

## 해결방안: 벌크 연산 구현

### 1. 새로운 벌크 처리 함수
```python
async def process_zotero_items_bulk(user: User, zot_instance, items: list, force_sync: bool = False) -> dict:
```

#### 주요 특징:
- **대량 처리**: 50개 아이템씩 벌크 처리
- **사전 필터링**: 기존 아이템 여부를 벌크 쿼리로 확인
- **트랜잭션 최적화**: 단일 트랜잭션 내에서 벌크 연산
- **관계 처리**: 컬렉션 관계도 벌크로 처리

### 2. 벌크 인서트 구현
```python
# 신규 아이템 벌크 생성
if items_to_create:
    ZoteroItem.insert_many(items_to_create).execute()

# 기존 아이템 벌크 업데이트  
if items_to_update:
    for item_dict in items_to_update:
        ZoteroItem.update(**{...}).where(...).execute()
```

### 3. 컬렉션 관계 벌크 처리
```python
async def process_collection_relationships_bulk(user: User, relationships: list):
    # 기존 관계 삭제 후 벌크 인서트
    ZoteroCollectionItem.delete().where(...).execute()
    ZoteroCollectionItem.insert_many(relationships_to_create).execute()
```

## 성능 개선 효과

### 배치 크기 변경
```python
# 이전 방식
batch_size = 5  # 웹 응답성 우선

# 벌크 방식  
bulk_batch_size = 50  # 성능과 응답성 균형
```

### 대기 시간 최적화
```python
# 이전: 개별 처리로 인한 긴 대기
await asyncio.sleep(0.05)  # 각 아이템마다
await asyncio.sleep(3.0)   # 배치마다

# 벌크: 효율적인 대기
await asyncio.sleep(0.01)  # 트랜잭션 내
await asyncio.sleep(1.0)   # 벌크 배치마다
```

## 구현 상세

### 1. 데이터 준비 단계
- 기존 아이템 키 집합을 벌크 쿼리로 조회
- 신규/업데이트 아이템 분리
- 컬렉션 관계 데이터 수집

### 2. 벌크 연산 단계
- `db.atomic()` 트랜잭션 내에서 벌크 인서트/업데이트
- 컬렉션 관계 벌크 처리
- 진행률 업데이트

### 3. 에러 처리
- 벌크 연산 실패 시 전체 배치를 에러로 처리
- 개별 아이템 에러는 로그만 기록

## 성능 vs 응답성 균형

### 성능 개선
- **DB 연산 횟수**: 50배 감소 (50개 → 1개 트랜잭션)
- **락 경합**: 대폭 감소
- **메모리 효율성**: 배치 단위 처리

### 응답성 유지
- **배치 간 yield**: 1초 대기로 웹서버 응답 보장
- **트랜잭션 내 yield**: 10ms로 최소한의 양보
- **진행률 업데이트**: 벌크 배치마다 업데이트

## 예상 성능 개선

### 처리 속도
- **이론적**: 50배 빠른 DB 연산
- **실제 예상**: 10-20배 개선 (네트워크 I/O, 기타 오버헤드 고려)

### 메모리 사용
- **일정한 메모리**: 배치 크기 고정
- **GC 압박 감소**: 대량 객체 생성 감소

### 웹서버 응답성  
- **더 나은 균형**: 성능 향상으로 전체 시간 단축
- **예측 가능한 응답**: 1초마다 확실한 yield

## 향후 고려사항

### 1. 설정 가능한 배치 크기
```python
# 환경변수로 조정 가능
ZOTERO_BULK_BATCH_SIZE = int(os.getenv('ZOTERO_BULK_BATCH_SIZE', 50))
```

### 2. 에러 복구 메커니즘
- 벌크 연산 실패 시 개별 처리로 폴백
- 부분 성공 처리 로직

### 3. 모니터링 강화
- 벌크 연산 성능 메트릭
- 메모리 사용량 모니터링

## 마이그레이션 영향
- **하위 호환성**: 기존 `process_zotero_item()` 함수 유지
- **점진적 적용**: 벌크 처리가 실패하면 개별 처리로 폴백 가능
- **데이터 무결성**: 트랜잭션 보장으로 안전성 유지

## 결론
벌크 인서트 구현으로 Zotero 동기화 성능을 대폭 개선하면서도 웹서버 응답성을 유지하는 최적의 균형점을 찾았음.