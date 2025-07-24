# Zotero 벌크 인서트 Authors 필드 오류 수정

## 날짜: 2025-07-24

## 문제 현상
Zotero 동기화 중 벌크 처리 과정에서 다음 오류 발생:
```
ERROR:app.main:Error in bulk processing: type object 'ZoteroItem' has no attribute 'authors'
```

## 문제 원인 분석

### 1. 모델 스키마와 코드 불일치
ZoteroItem 모델의 실제 필드명과 벌크 처리 코드에서 사용하는 필드명이 달랐음:

**모델 정의 (models.py)**:
```python
class ZoteroItem(BaseModel):
    # ... 기타 필드들
    title = CharField(null=True, index=True)
    authors_text = TextField(null=True)  # "Author1; Author2; Author3"
    # ... 계속
```

**벌크 처리 코드 (main.py:4857)**:
```python
item_dict = {
    # ... 기타 필드들
    'authors': json.dumps([]),  # ❌ 잘못된 필드명
    # ... 계속
}
```

### 2. 오류 발생 지점
- **함수**: `process_zotero_items_bulk()`
- **위치**: `/home/jikhanjung/projects/RefServerLite/app/main.py:4857`
- **원인**: 모델에 존재하지 않는 `authors` 필드를 사용하여 벌크 인서트 시도

## 해결방안

### 필드명 수정
벌크 처리 코드에서 올바른 필드명 사용:

```python
# 수정 전
'authors': json.dumps([]),  # ❌ 존재하지 않는 필드

# 수정 후  
'authors_text': json.dumps([]),  # ✅ 올바른 필드명
```

## 수정 상세

### 변경된 파일
- `/home/jikhanjung/projects/RefServerLite/app/main.py`

### 변경된 라인
- **라인 4857**: `'authors'` → `'authors_text'`

### 수정 코드
```python
item_dict = {
    'zotero_key': item_key,
    'library_id': user.zotero_library_id,
    'user': user.id,
    'version': item['version'],
    'item_type': item_data.get('itemType', 'unknown'),
    'parent_key': item_data.get('parentItem'),
    'is_attachment': (item_data.get('itemType') == 'attachment'),
    'content_type': item_data.get('contentType'),
    'filename': item_data.get('filename'),
    'title': item_data.get('title', ''),
    'authors_text': json.dumps([]),  # ✅ 수정됨
    'data': json.dumps(item_data),
    'synced_at': datetime.datetime.now()
}
```

## 근본 원인 분석

### 1. 모델 필드명 일관성 부족
- 다른 부분의 코드에서는 `authors_text` 필드를 올바르게 사용
- 벌크 처리 함수만 잘못된 필드명 사용
- 코드 리뷰 과정에서 놓친 오타

### 2. 개발 과정에서의 필드명 변경
- 초기 개발 시 `authors` 필드명으로 시작
- 모델 설계 변경으로 `authors_text`로 변경
- 일부 코드에서 업데이트 누락

## 예방 방안

### 1. 모델 필드 상수화
```python
# 향후 개선안
class ZoteroItemFields:
    AUTHORS_TEXT = 'authors_text'
    TITLE = 'title'
    # ... 기타 필드들

# 사용
item_dict = {
    ZoteroItemFields.AUTHORS_TEXT: json.dumps([]),
    ZoteroItemFields.TITLE: item_data.get('title', ''),
}
```

### 2. 타입 힌트 강화
```python
from typing import TypedDict

class ZoteroItemDict(TypedDict):
    zotero_key: str
    authors_text: str
    title: str
    # ... 기타 필드들
```

### 3. 단위 테스트 강화
- 벌크 인서트 기능에 대한 단위 테스트 추가
- 모델 필드명 일관성 검증 테스트

## 성능 영향

### 수정 전
- 벌크 처리 실패로 개별 처리로 폴백
- 성능 저하 및 동기화 실패

### 수정 후
- 벌크 처리 정상 동작
- 100개 아이템 페이지 단위로 효율적 처리
- 웹서버 응답성 유지

## 테스트 결과
- ✅ 벌크 인서트 오류 해결
- ✅ Zotero 동기화 정상 동작
- ✅ 실시간 아이템 표시 작동
- ✅ 웹서버 응답성 유지

## 결론
단순한 필드명 오타였지만 전체 벌크 처리 시스템을 무력화시키는 중요한 버그였음. 모델 필드명의 일관성과 코드 리뷰의 중요성을 재확인할 수 있었음.