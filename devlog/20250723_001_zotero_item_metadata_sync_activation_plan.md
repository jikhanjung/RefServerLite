# Zotero Item 메타데이터 동기화 활성화 계획

**날짜:** 2025-07-23

## 목표

Zotero 라이브러리의 모든 아이템 메타데이터를 RefServerLite에 동기화하고, PDF 첨부파일만 `Paper` 문서로 처리하도록 기존 로직을 활성화 및 검증합니다.

## Phase 0: ZoteroItem 테이블 구조 개선

### 현재 메타데이터 저장 방식의 문제점

현재 시스템은 이중 메타데이터 저장 방식을 사용합니다:

1. **ZoteroItem 테이블**: 모든 Zotero 아이템의 전체 메타데이터를 `data` JSON 필드에 저장
2. **Metadata 테이블**: PDF 문서(Paper)에 대해서만 구조화된 메타데이터를 별도 저장

이로 인한 문제점:
- **검색의 복잡성**: JSON 필드 내 데이터 검색이 어려움
- **성능 이슈**: 인덱싱이 불가능한 JSON 필드
- **일관성 부족**: 비-PDF 아이템은 구조화된 검색 불가
- **중복 저장**: 같은 메타데이터가 두 곳에 저장됨

### 해결책: ZoteroItem 테이블 확장

자주 검색되는 메타데이터 필드를 별도 컬럼으로 추가하여 빠른 검색과 정렬을 지원:

```python
class ZoteroItem(BaseModel):
    # 기존 필드들...
    zotero_key = CharField(unique=True, index=True)
    library_id = CharField(index=True) 
    item_type = CharField()
    data = TextField()  # JSON - 전체 메타데이터 보존용
    
    # 새로 추가할 검색 최적화 필드들
    title = CharField(null=True, index=True)
    authors_text = TextField(null=True)  # 검색용 - "Author1; Author2; Author3"
    journal = CharField(null=True, index=True) 
    year = IntegerField(null=True, index=True)
    doi = CharField(null=True, index=True)
    abstract = TextField(null=True)
    
    # 편의 메서드 추가
    def get_authors_list(self) -> List[str]:
        """Get authors as a list"""
        if self.authors_text:
            return [author.strip() for author in self.authors_text.split(';') if author.strip()]
        return []
    
    def set_authors_from_creators(self, creators: List[dict]):
        """Set authors from Zotero creators data"""
        authors = []
        for creator in creators:
            if creator.get('creatorType') == 'author':
                name_parts = []
                if creator.get('firstName'):
                    name_parts.append(creator['firstName'])
                if creator.get('lastName'):
                    name_parts.append(creator['lastName'])
                if name_parts:
                    authors.append(' '.join(name_parts))
        self.authors_text = '; '.join(authors) if authors else None
    
    def extract_year_from_date(self, date_str: str) -> Optional[int]:
        """Extract year from Zotero date string"""
        if not date_str:
            return None
        # Zotero 날짜 형식: "2023-01-15", "2023", "01/2023" 등
        import re
        year_match = re.search(r'\b(19|20)\d{2}\b', str(date_str))
        return int(year_match.group()) if year_match else None
```

### 구현 단계

1. **데이터베이스 마이그레이션**
   ```sql
   ALTER TABLE zoteroitem ADD COLUMN title VARCHAR(500);
   ALTER TABLE zoteroitem ADD COLUMN authors_text TEXT;
   ALTER TABLE zoteroitem ADD COLUMN journal VARCHAR(300);
   ALTER TABLE zoteroitem ADD COLUMN year INTEGER;
   ALTER TABLE zoteroitem ADD COLUMN doi VARCHAR(200);
   ALTER TABLE zoteroitem ADD COLUMN abstract TEXT;
   
   CREATE INDEX idx_zoteroitem_title ON zoteroitem(title);
   CREATE INDEX idx_zoteroitem_journal ON zoteroitem(journal);
   CREATE INDEX idx_zoteroitem_year ON zoteroitem(year);
   CREATE INDEX idx_zoteroitem_doi ON zoteroitem(doi);
   ```

2. **process_zotero_item 함수 수정**
   ```python
   # 기존: zotero_item.set_data(item_data) 이후에 추가
   
   # 구조화된 메타데이터 추출 및 저장
   zotero_item.title = item_data.get('title')
   zotero_item.journal = (item_data.get('publicationTitle') or 
                         item_data.get('journalAbbreviation'))
   zotero_item.doi = item_data.get('DOI')
   zotero_item.abstract = item_data.get('abstractNote')
   zotero_item.year = zotero_item.extract_year_from_date(item_data.get('date'))
   
   # 저자 정보 처리
   creators = item_data.get('creators', [])
   zotero_item.set_authors_from_creators(creators)
   ```

3. **검색 API 개선**
   - 통합된 Zotero 아이템 검색 엔드포인트 구현
   - 제목, 저자, 저널, 연도별 필터링 지원
   - 페이지네이션과 정렬 기능

### 장점

- **빠른 검색**: 인덱싱된 컬럼으로 고속 검색
- **통합된 검색**: PDF/비-PDF 구분 없이 모든 아이템 검색 가능
- **유연성**: JSON `data` 필드로 전체 메타데이터 보존
- **확장성**: 필요에 따라 추가 검색 필드 확장 가능

## Phase 1: 백엔드 로직 활성화 및 조정

1.  **`app/main.py` 파일 수정 - `process_zotero_sync_job` 함수:**
    *   **임시 스킵 블록 제거:** `TEMPORARY: Skipping item sync for collection testing` 주석 블록과 그 안에 있는 `return` 문을 제거합니다.
    *   **아이템 가져오기 로직 활성화:** Zotero API에서 아이템을 가져오는 다음 코드 블록의 주석을 해제합니다.
        ```python
        # Determine sync parameters
        job_params = job.get_parameters()
        params = {}
        if job_params.get('limit'):
            params['limit'] = job_params['limit']

        # Incremental sync unless force_full_sync is True
        if not job_params.get('force_full_sync') and user.zotero_last_sync:
            import time
            params['since'] = int(user.zotero_last_sync.timestamp())

        # Fetch items
        if job_params.get('collection_id'):
            items = zot.collection_items(job_params['collection_id'], **params)
        else:
            items = zot.items(**params)
        ```
    *   **아이템 처리 루프 활성화:** 가져온 아이템들을 순회하며 `process_zotero_item` 함수를 호출하는 다음 루프의 주석을 해제합니다.
        ```python
        # Update progress - process items
        job.current_step = 'processing_items'
        job.progress_percentage = 30
        job.total_steps = len(items) + 10 # Adjust total_steps based on actual items
        job.save()

        processed_count = 0
        success_count = 0
        error_count = 0
        pdf_count = 0

        for item in items:
            # Check if job was cancelled every 10 items
            if processed_count % 10 == 0 and check_job_cancelled(job_id):
                logger.info(f"Zotero sync job {job_id} was cancelled during item processing")
                return

            # Add small delay between items to reduce CPU load and allow other requests
            if processed_count % 5 == 0: # Every 5 items
                await asyncio.sleep(0.1) # 100ms pause

            try:
                result = await process_zotero_item(user, zot, item, job_params.get('force_full_sync', False))

                if result['processed']:
                    success_count += 1
                    if result['pdf_created']:
                        pdf_count += 1
                elif result['skipped']:
                    pass
                else:
                    error_count += 1

                processed_count += 1

                # Update progress
                progress = 30 + (processed_count / len(items)) * 60
                job.progress_percentage = int(progress)
                job.save()

            except Exception as e:
                logger.error(f"Error processing item {item['key']}: {e}")
                error_count += 1
                processed_count += 1
                continue
        ```
    *   **최종 동기화 시간 및 작업 결과 업데이트:** 아이템 처리 루프가 완료된 후 `user.zotero_last_sync`를 현재 시간으로 업데이트하고, `job.set_result`를 통해 최종 동기화 결과를 정확하게 반영하도록 합니다.

2.  **`app/main.py` 파일 검토 - `process_zotero_item` 함수:**
    *   **메타데이터 저장 확인:** `zotero_item.set_data(item_data)` 라인이 모든 Zotero 아이템의 전체 메타데이터(PDF가 아닌 아이템 포함)를 `ZoteroItem.data` 필드에 올바르게 저장하는지 확인합니다. (기존 커밋에서 이미 구현되어 있을 것으로 예상됩니다.)
    *   **PDF 조건부 처리 확인:** `if zotero_item.is_pdf_attachment():` 조건문이 PDF 첨부파일에 대해서만 PDF 다운로드 및 `Paper` 생성을 시도하도록 올바르게 작동하는지 확인합니다. PDF가 아닌 아이템은 이 블록을 건너뛰고 `ZoteroItem` 레코드만 업데이트되어야 합니다.

## Phase 2: 테스트 및 검증 (Claude Code가 구현 후 진행)

1.  **단위 테스트:**
    *   `process_zotero_item` 함수가 다양한 Zotero 아이템 타입(저널 논문, 책, 웹페이지, 첨부파일 등)을 올바르게 처리하는지 확인합니다. 특히, PDF가 아닌 아이템의 경우 PDF 관련 작업 없이 메타데이터만 `ZoteroItem.data`에 저장되는지 검증합니다.
2.  **통합 테스트:**
    *   다수의 PDF 및 비-PDF 아이템이 혼합된 Zotero 라이브러리를 가진 사용자로 동기화를 시작합니다.
    *   RefServerLite 데이터베이스의 `ZoteroItem` 테이블에 모든 Zotero 아이템의 메타데이터가 올바르게 동기화되었는지 확인합니다.
    *   오직 PDF 첨부파일에 대해서만 `Paper` 레코드가 생성되고 PDF 처리 파이프라인이 트리거되는지 확인합니다.
    *   관리자 대시보드의 작업 모니터링 페이지에서 동기화 작업의 진행률과 상태가 정확하게 업데이트되는지 확인합니다.
    *   Zotero 라이브러리에 새로운 아이템을 추가한 후 증분 동기화가 올바르게 작동하는지 테스트합니다.

## Phase 3: 추가 고려사항 및 최적화

### 1. **대용량 라이브러리 처리**
대규모 Zotero 라이브러리(수천 개 이상의 아이템)를 처리할 때 메모리 및 성능 이슈를 방지하기 위한 배치 처리 구현:
```python
# 배치 크기 설정
BATCH_SIZE = 100

# 배치 단위로 처리
for i in range(0, len(items), BATCH_SIZE):
    batch = items[i:i+BATCH_SIZE]
    # 배치 처리 로직
    # 각 배치 완료 후 메모리 정리 고려
```

### 2. **메모리 최적화**
전체 아이템을 한 번에 메모리에 로드하는 대신 스트리밍 방식 사용:
```python
# pyzotero의 iterate() 메서드 활용
for item in zot.iterate_items():
    # 아이템을 하나씩 처리하여 메모리 사용량 최소화
    await process_zotero_item(user, zot, item, force_full_sync)
```

### 3. **에러 복구 전략**
동기화 중 실패한 아이템을 추적하고 재시도 메커니즘 구현:
```python
# 실패한 아이템 추적
failed_items = []

try:
    result = await process_zotero_item(user, zot, item, force_full_sync)
except Exception as e:
    failed_items.append({
        'item_key': item['key'],
        'error': str(e),
        'timestamp': datetime.datetime.now().isoformat()
    })

# 작업 결과에 실패 정보 포함
if error_count > 0:
    job.set_result({
        'items_synced': success_count,
        'pdfs_created': pdf_count,
        'errors': error_count,
        'failed_items': failed_items  # 나중에 재시도 가능
    })
```

### 4. **PDF 다운로드 우선순위 관리**
사용자 경험 최적화를 위한 스마트 PDF 다운로드 전략:
- 최근 추가/수정된 아이템의 PDF 우선 다운로드
- 사용자가 자주 접근하는 컬렉션의 PDF 우선 처리
- 파일 크기 기반 우선순위 (작은 파일 먼저)

### 5. **동기화 상태 세분화**
더 상세한 동기화 상태 추적:
```python
# ZoteroItem 모델에 동기화 상태 필드 추가 고려
sync_status = CharField(default='pending')  # pending, synced, failed, pdf_downloading, pdf_ready
last_sync_attempt = DateTimeField(null=True)
sync_error_message = TextField(null=True)
```

### 6. **사용자 인터페이스 개선**
동기화 옵션을 사용자가 제어할 수 있도록 UI 확장:
- "Metadata Only" vs "Include PDFs" 선택 옵션
- 특정 컬렉션만 동기화하는 옵션
- 동기화 일시정지/재개 기능
- 실시간 동기화 통계 표시 (처리된 아이템 수, 남은 시간 예상 등)

### 7. **성능 모니터링**
동기화 성능 메트릭 수집:
```python
# 동기화 시작 시간, 종료 시간 기록
# 아이템당 평균 처리 시간 계산
# 병목 구간 식별을 위한 로깅
logger.info(f"Average processing time per item: {total_time/processed_count:.2f}s")
```

### 8. **증분 동기화 개선**
Zotero API의 `since` 파라미터 외에도 `version` 기반 동기화 고려:
```python
# 각 아이템의 version을 저장하고 비교
if existing_item.version < item['version']:
    # 업데이트 필요
```
