# Zotero Collections API 최적화 분석

## 날짜: 2025-07-24

## 이슈 발견
사용자 라이브러리 페이지에서 Zotero sync 시 collection 정보를 가져올 때 `all_collections()` 메서드가 내부적으로 여러 번의 API 호출을 하는 것을 발견.

## 현재 구현 분석

### pyzotero의 `all_collections()` 메서드 내부 동작

```python
def all_collections(self, collid=None):
    """Retrieve all collections and subcollections. Works for top-level collections
    or for a specific collection. Works at all collection depths.
    """
    all_collections = []

    def subcoll(clct):
        """Recursively add collections to a flat master list"""
        all_collections.append(clct)
        if clct["meta"].get("numCollections", 0) > 0:
            # add collection to master list & recur with all child collections
            [
                subcoll(c)
                for c in self.everything(self.collections_sub(clct["data"]["key"]))
            ]

    # select all top-level collections or a specific collection and children
    if collid:
        toplevel = [self.collection(collid)]
    else:
        toplevel = self.everything(self.collections_top())
    [subcoll(collection) for collection in toplevel]
    return all_collections
```

### API 호출 패턴
1. **최상위 컬렉션 가져오기**: `self.everything(self.collections_top())` - 최소 1회 API 호출
2. **재귀적 하위 컬렉션 조회**: 각 컬렉션에 하위 컬렉션이 있으면 `self.collections_sub(key)` 추가 호출
3. **총 API 호출 횟수**: 1 + (하위 컬렉션을 가진 컬렉션의 수)

예시:
- 10개의 최상위 컬렉션 중 5개가 하위 컬렉션을 가진 경우
- 총 6회의 API 호출 발생 (1 + 5)

## 개선 방안

### Zotero API v3의 collections 엔드포인트 활용
Zotero API는 실제로 모든 컬렉션을 한 번에 가져올 수 있는 엔드포인트를 제공:

```python
# 현재 방식 (여러 번의 API 호출)
collections = zot_instance.all_collections()

# 개선된 방식 (API 호출 최소화)
collections = zot_instance.everything(zot_instance.collections())
```

### 차이점
- `all_collections()`: 계층 구조를 재귀적으로 탐색하며 여러 번 API 호출
- `everything(collections())`: 모든 컬렉션을 한 번의 API 호출 시퀀스로 가져옴 (페이지네이션 자동 처리)

### 장점
1. **성능 향상**: API 호출 횟수 대폭 감소
2. **속도 개선**: 네트워크 왕복 시간 감소
3. **API 제한 회피**: Zotero API rate limit에 걸릴 가능성 감소

## 구현 제안

`app/main.py`의 `sync_zotero_collections` 함수 수정:

```python
async def sync_zotero_collections(user: User, zot_instance) -> int:
    """Sync Zotero collections"""
    import json
    import datetime
    try:
        # 기존 코드
        # collections = zot_instance.all_collections()
        
        # 개선된 코드
        collections = zot_instance.everything(zot_instance.collections())
        logger.info(f"📊 Retrieved {len(collections)} collections using everything(collections()) method")
        
        # 이하 동일...
```

## 추가 고려사항

1. **기존 데이터와의 호환성**: 두 메서드 모두 동일한 형식의 컬렉션 데이터를 반환하므로 호환성 문제 없음
2. **메모리 사용량**: 대량의 컬렉션이 있는 경우에도 `everything()` 메서드가 자동으로 페이지네이션을 처리
3. **에러 처리**: API 호출 실패 시 재시도 로직은 동일하게 적용 가능

## 결론
`all_collections()` 대신 `everything(collections())`를 사용하면 API 호출 횟수를 크게 줄이고 동기화 성능을 향상시킬 수 있다.