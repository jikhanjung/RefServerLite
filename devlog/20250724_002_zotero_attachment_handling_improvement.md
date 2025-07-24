# Zotero Attachment 처리 개선

## 날짜: 2025-07-24

## 요구사항
- Zotero 아이템 목록에서 attachment가 parent item이 있는 경우 숨기기
- Parent item이 없는 standalone attachment만 목록에 표시
- Parent item의 detail view에서 모든 attachment 확인 가능

## 구현 내용

### 1. API 엔드포인트 수정 (`/api/v1/users/me/zotero/items`)

#### 변경 전
```python
# 모든 ZoteroItem을 가져옴
zotero_items_query = ZoteroItem.select().where(ZoteroItem.user == current_user)
```

#### 변경 후
```python
# attachment 중 parent가 있는 것은 제외
zotero_items_query = ZoteroItem.select().where(
    ZoteroItem.user == current_user,
    (ZoteroItem.is_attachment == False) | (ZoteroItem.parent_key.is_null())
)
```

### 2. 아이템 상세 페이지 개선

#### 백엔드 (`user_zotero_item_detail` 함수)
- Parent item에 속한 모든 attachment 조회 추가
- 각 attachment의 RefServerLite 연결 상태 확인
- 템플릿에 attachments 데이터 전달

```python
# Get attachments for this item
attachments = []
attachment_query = ZoteroItem.select().where(
    ZoteroItem.parent_key == zotero_item.zotero_key,
    ZoteroItem.user == current_user,
    ZoteroItem.is_attachment == True
)
```

#### 프론트엔드 (user_zotero_item_detail.html)
- Attachments 카드 섹션 추가
- 각 attachment별로:
  - 파일명, 콘텐츠 타입 표시
  - RefServerLite 가져오기 상태 표시
  - 가져오지 않은 PDF는 Import 버튼 제공
  - 가져온 PDF는 View 버튼 제공

### 3. UI/UX 개선사항

#### 아이템 목록
- Parent item만 표시되어 목록이 더 깔끔해짐
- Standalone attachment는 계속 표시됨 (고아 파일 방지)

#### 아이템 상세
- 모든 attachment를 한눈에 확인 가능
- 각 attachment의 import 상태 명확히 표시
- 개별 attachment import 기능 제공

## 기술적 고려사항

### 성능
- `parent_key.is_null()` 조건으로 효율적인 필터링
- attachment 조회 시 별도 쿼리로 N+1 문제 방지

### 호환성
- 기존 데이터 구조 유지
- API 응답 형식 변경 없음 (필터링만 추가)

## 결과
- 사용자는 주요 문헌 아이템에 집중 가능
- Attachment 관리가 더 직관적으로 개선
- Parent-child 관계가 UI에 명확히 반영됨