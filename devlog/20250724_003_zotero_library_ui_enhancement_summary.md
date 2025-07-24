# Zotero Library UI 개선 작업 종합 요약

## 날짜: 2025-07-24

## 작업 개요
사용자 라이브러리 페이지에서 Zotero 아이템의 PDF 연결 상태와 attachment 정보를 명확히 표시하고, attachment 목록 표시 방식을 개선한 종합적인 UI 개선 작업.

## 주요 개선 사항

### 1. Paper 연결 상태 및 Zotero Attachment 정보 표시

#### 기존 문제점
- Zotero sync 시 `-attachment` 필터로 첨부파일 정보를 제외하고 가져옴
- 라이브러리에서 각 아이템의 PDF 상태를 확인할 수 없음
- RefServerLite에 가져온 PDF와 Zotero의 attachment 구분이 어려움

#### 해결방안
1. **Zotero Sync 수정**
   - `itemType='-attachment'` 필터 제거
   - 모든 아이템(attachment 포함) 동기화
   - Parent item과 attachment 관계 유지

2. **API Response 개선** (`/api/v1/users/me/zotero/items`)
   ```python
   # 추가된 필드들
   'attachment_count': attachment_count,  # Zotero PDF 첨부파일 개수
   'has_pdf': paper_id is not None,      # RefServerLite PDF 존재 여부
   'has_zotero_attachment': attachment_count > 0  # Zotero attachment 존재 여부
   ```

3. **UI 배지 시스템** (user_zotero_library.html)
   - 🟦 **PDF in Library**: RefServerLite에 이미 가져온 PDF
   - 🟢 **N PDF(s)**: Zotero에 있는 PDF 첨부파일 개수
   - 🔘 **No PDF**: Zotero에 PDF 첨부파일 없음

### 2. Attachment 목록 표시 방식 개선

#### 기존 문제점
- Parent item과 attachment가 동일한 레벨에서 표시됨
- 목록이 복잡하고 관리하기 어려움
- Attachment의 parent-child 관계가 UI에 반영되지 않음

#### 해결방안
1. **목록 필터링**
   ```python
   # Parent가 있는 attachment는 목록에서 제외
   zotero_items_query = ZoteroItem.select().where(
       ZoteroItem.user == current_user,
       (ZoteroItem.is_attachment == False) | (ZoteroItem.parent_key.is_null())
   )
   ```

2. **상세 페이지에서 attachment 표시**
   - Parent item 상세 페이지에 "Attachments" 카드 추가
   - 각 attachment의 상태 정보 표시:
     - 파일명 및 콘텐츠 타입
     - RefServerLite 가져오기 상태
     - 개별 Import/View 버튼

### 3. 사용자 경험 개선

#### 액션 버튼 최적화
- **Import PDF**: Zotero에는 PDF가 있지만 RefServerLite에는 없는 경우만 표시
- **View PDF**: RefServerLite에 PDF가 있는 경우 문서 보기 링크 추가
- **개별 Attachment Import**: 상세 페이지에서 각 attachment별로 import 가능

#### 정보 표시 개선
- 아이템별 PDF 상태를 한눈에 확인 가능
- Attachment 개수와 상태 명확히 표시
- Parent-child 관계가 UI 구조에 반영됨

## 기술적 구현 상세

### Backend 변경사항
1. **main.py**
   - `get_user_zotero_items()`: attachment 정보 추가, 필터링 로직 개선
   - `user_zotero_item_detail()`: attachment 조회 및 상태 확인 로직 추가
   - `process_zotero_sync_job()`: attachment 포함 동기화

2. **Database Query 최적화**
   - N+1 쿼리 문제 방지를 위한 효율적인 attachment 조회
   - Parent-child 관계 기반 필터링

### Frontend 변경사항
1. **user_zotero_library.html**
   - 배지 시스템으로 PDF 상태 표시
   - 조건부 액션 버튼 표시

2. **user_zotero_item_detail.html**
   - Attachments 카드 섹션 추가
   - 개별 attachment import 기능
   - 상태 기반 버튼 표시

## 성능 고려사항
- **API 호출 최소화**: attachment 정보를 기존 쿼리에 포함하여 추가 API 호출 없음
- **효율적인 필터링**: 데이터베이스 레벨에서 조건 처리
- **Lazy Loading**: attachment 정보는 상세 페이지에서만 로드

## 호환성
- **기존 데이터**: 모든 변경사항이 기존 데이터와 호환
- **API 구조**: 기존 API 응답에 필드 추가 (Breaking change 없음)
- **UI/UX**: 기존 워크플로우 유지하면서 기능 개선

## 사용자 혜택
1. **명확한 상태 인식**: 각 아이템의 PDF 상태를 즉시 파악 가능
2. **효율적인 관리**: Parent item 중심의 깔끔한 목록 구조
3. **편리한 접근**: 상세 페이지에서 모든 attachment 한번에 관리
4. **직관적인 워크플로우**: 가져오기 상태에 따른 적절한 액션 제공

## 향후 개선 가능 영역
1. **Bulk Import**: 여러 attachment 동시 가져오기
2. **Progress Tracking**: Import 진행상황 실시간 표시
3. **Attachment Preview**: PDF 미리보기 기능
4. **Smart Filtering**: PDF 상태별 필터링 옵션