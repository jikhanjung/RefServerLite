# Zotero 연동 및 API 기반 문서 추가 기능 구현 계획

## 개요

Zotero 라이브러리의 논문 정보와 첨부파일을 RefServerLite로 가져오는 기능을 구현합니다. 이를 위해 파일과 메타데이터(제목, 저자, 출판 연도)를 함께 입력받는 새로운 백엔드 API를 먼저 개발하고, 이 API를 사용하여 Zotero와 연동하는 클라이언트 스크립트를 작성합니다.

---

### **Phase 1: 백엔드 API 구현**

**목표**: PDF 파일과 핵심 메타데이터를 `multipart/form-data`로 받아 처리하는 API 엔드포인트를 개발합니다. 사용자가 제공한 메타데이터를 우선적으로 사용하도록 시스템을 수정합니다.

#### **1단계: 데이터베이스 모델 수정 (`app/models.py`)**

**목적**: 사용자가 입력한 메타데이터와 시스템이 자동으로 추출한 메타데이터를 구분하기 위함입니다.

*   **파일**: `app/models.py`
*   **변경 사항**:
    *   `Metadata` 모델에 `source` 필드를 추가합니다.
        *   `source = CharField(default='extracted', index=True)`
        *   값의 의미:
            *   `'extracted'` (기본값): 시스템이 PDF에서 자동으로 추출한 메타데이터.
            *   `'user_api'`: API를 통해 사용자가 직접 제공한 메타데이터.

*   **후속 조치**: 모델 변경 후, 터미널에서 `python migrate.py`를 실행하여 데이터베이스 마이그레이션 스크립트를 생성해야 합니다.

#### **2단계: 신규 API 엔드포인트 추가 (`app/main.py`)**

**목적**: 파일과 메타데이터를 함께 수신하는 API를 구현합니다.

*   **파일**: `app/main.py`
*   **신규 엔드포인트**: `POST /api/v1/papers/upload_with_metadata`
*   **요청 형식**: `multipart/form-data`
    *   `file`: PDF 파일 (`UploadFile`)
    *   `title`: 논문 제목 (`Form`)
    *   `authors`: 저자 목록 (JSON 형식의 문자열, 예: `["Author A", "Author B"]`) (`Form`)
    *   `year`: 출판 연도 (`Form`)
*   **구현 로직**:
    1.  PDF 파일을 `data/pdfs/` 디렉토리에 저장합니다.
    2.  `Paper` 객체를 생성합니다.
    3.  전달받은 메타데이터로 `Metadata` 객체를 생성하고 `source`를 `'user_api'`로 설정하여 저장합니다.
    4.  문서 처리를 위한 `ProcessingJob`을 생성합니다.
    5.  성공 응답으로 `job_id`를 반환합니다.

#### **3단계: 처리 파이프라인 수정 (`app/pipeline.py`)**

**목적**: 사용자가 입력한 메타데이터가 자동 추출 로직에 의해 덮어쓰이는 것을 방지합니다.

*   **파일**: `app/pipeline.py`
*   **대상 함수**: `_extract_metadata`
*   **변경 로직**:
    *   함수 초입에서 해당 논문의 메타데이터 `source`가 `'user_api'`인지 확인합니다.
    *   `'user_api'`인 경우, 메타데이터 자동 추출 단계를 건너뛰고 해당 단계를 '완료' 처리합니다.

---

### **Phase 2: Zotero 연동 스크립트 작성**

**목표**: Zotero 라이브러리에서 논문 정보와 PDF를 가져와 새로 만든 백엔드 API를 호출하는 Python 스크립트를 작성합니다.

#### **1단계: 필요 라이브러리 추가**

*   **파일**: `requirements.txt`
*   **추가 라이브러리**:
    *   `pyzotero`: Zotero API와 상호작용
    *   `requests`: 백엔드 API에 HTTP 요청

#### **2단계: 연동 스크립트 작성**

*   **신규 파일**: `scripts/import_from_zotero.py`
*   **구현 로직**:
    1.  **설정**: Zotero `library_id`, `api_key`, RefServerLite API 주소를 설정합니다.
    2.  **연결**: `pyzotero`를 사용하여 Zotero 라이브러리에 연결합니다.
    3.  **데이터 가져오기**: Zotero 라이브러리에서 모든 아이템을 가져옵니다.
    4.  **아이템 처리**:
        *   각 아이템을 순회하며 PDF 첨부파일이 있는지 확인합니다.
        *   논문 메타데이터(`title`, `creators`, `date`)를 추출합니다.
        *   PDF 파일을 다운로드합니다.
        *   `requests`를 사용하여 백엔드 API (`/api/v1/papers/upload_with_metadata`)를 호출하고, 메타데이터와 PDF 파일을 전송합니다.
    5.  **결과 출력**: 처리 결과를 콘솔에 로깅합니다.

---

### **구현 요약**

1.  **의존성 추가**: `requirements.txt`에 `PyZotero`와 `requests` 추가.
2.  **모델 변경**: `app/models.py`에 `source` 필드 추가.
3.  **마이그레이션**: `python migrate.py` 실행.
4.  **API 개발**: `app/main.py`에 신규 엔드포인트 구현.
5.  **파이프라인 수정**: `app/pipeline.py`에서 메타데이터 추출 로직 수정.
6.  **스크립트 작성**: `scripts/import_from_zotero.py` 구현.

---

### **보완 사항 및 개선 제안**

#### **1. 오류 처리 및 안정성 강화**

**문제점**: 현재 계획에는 다양한 오류 상황에 대한 처리 방안이 누락되어 있습니다.

**개선 방안**:
- **Zotero API 장애 처리**: 
  - 연결 실패 시 재시도 로직 구현 (exponential backoff)
  - 타임아웃 설정 추가
  - 명확한 오류 메시지 출력
  
- **중복 문서 처리**:
  - 파일명 또는 제목 기반 중복 검사 로직 추가
  - 중복 발견 시 처리 옵션: 건너뛰기, 업데이트, 새 버전으로 추가
  - `Paper` 모델에 `zotero_key` 필드 추가 고려
  
- **Rate Limiting 대응**:
  - Zotero API의 rate limit (기본: 100 requests/hour) 고려
  - 요청 간 지연 시간 설정
  - Rate limit 도달 시 대기 및 재개 로직

#### **2. 인증 및 보안 강화**

**문제점**: 새로운 API 엔드포인트가 인증 없이 누구나 접근 가능합니다.

**구현 방안**:
```python
# app/main.py에 추가
@router.post("/api/v1/papers/upload_with_metadata")
async def upload_with_metadata(
    file: UploadFile = File(...),
    title: str = Form(...),
    authors: str = Form(...),
    year: Optional[int] = Form(None),
    current_user: User = Depends(get_current_user)  # 인증 추가
):
    # 관리자 권한 확인
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
```

#### **3. 대량 가져오기 최적화**

**문제점**: 대규모 Zotero 라이브러리 가져오기 시 성능 및 안정성 문제 발생 가능.

**개선 방안**:

- **배치 처리 구현**:
  ```python
  # scripts/import_from_zotero.py
  BATCH_SIZE = 50  # 한 번에 처리할 아이템 수
  
  def import_in_batches(items, batch_size=BATCH_SIZE):
      for i in range(0, len(items), batch_size):
          batch = items[i:i+batch_size]
          process_batch(batch)
          time.sleep(1)  # API rate limit 고려
  ```

- **진행 상황 추적**:
  ```python
  # 진행 상황을 파일에 저장
  import json
  
  class ImportProgress:
      def __init__(self, progress_file="zotero_import_progress.json"):
          self.progress_file = progress_file
          self.load_progress()
      
      def save_progress(self, processed_keys):
          with open(self.progress_file, 'w') as f:
              json.dump({"processed": list(processed_keys)}, f)
      
      def load_progress(self):
          try:
              with open(self.progress_file, 'r') as f:
                  data = json.load(f)
                  return set(data.get("processed", []))
          except FileNotFoundError:
              return set()
  ```

- **필터링 옵션 추가**:
  ```python
  # 커맨드라인 인자로 필터 옵션 제공
  parser = argparse.ArgumentParser()
  parser.add_argument('--collection', help='특정 컬렉션만 가져오기')
  parser.add_argument('--since', help='특정 날짜 이후 항목만 (YYYY-MM-DD)')
  parser.add_argument('--limit', type=int, help='가져올 최대 항목 수')
  parser.add_argument('--tags', nargs='+', help='특정 태그가 있는 항목만')
  ```

#### **4. 저장 공간 관리**

**문제점**: 대량의 PDF 다운로드 시 디스크 공간 부족 가능.

**개선 방안**:
- **사전 공간 확인**:
  ```python
  import shutil
  
  def check_disk_space(required_gb=10):
      stat = shutil.disk_usage("/app/data/pdfs")
      free_gb = stat.free / (1024**3)
      if free_gb < required_gb:
          raise Exception(f"Insufficient disk space: {free_gb:.1f}GB available")
  ```

- **스트리밍 다운로드**: 메모리 효율적인 파일 다운로드
  ```python
  def download_pdf_streaming(url, filepath):
      with requests.get(url, stream=True) as r:
          r.raise_for_status()
          with open(filepath, 'wb') as f:
              for chunk in r.iter_content(chunk_size=8192):
                  f.write(chunk)
  ```

#### **5. 추가 기능 제안**

**5.1 Dry-run 모드**:
```python
# scripts/import_from_zotero.py
parser.add_argument('--dry-run', action='store_true', 
                   help='실제 가져오기 없이 시뮬레이션만 수행')

if args.dry_run:
    print(f"[DRY RUN] Would import: {title}")
    print(f"  Authors: {authors}")
    print(f"  Year: {year}")
    print(f"  PDF size: {pdf_size}MB")
else:
    # 실제 가져오기 수행
```

**5.2 Zotero 연동 정보 저장**:
```python
# app/models.py에 추가
class ZoteroLink(BaseModel):
    paper = ForeignKeyField(Paper, backref='zotero_link', unique=True)
    zotero_key = CharField(unique=True, index=True)
    zotero_version = IntegerField()
    library_id = CharField()
    collection_keys = TextField(null=True)  # JSON array
    tags = TextField(null=True)  # JSON array
    imported_at = DateTimeField(default=datetime.now)
```

**5.3 설정 파일 지원**:
```yaml
# config/zotero_import.yml
zotero:
  library_id: "YOUR_LIBRARY_ID"
  api_key: "YOUR_API_KEY"
  
refserver:
  api_url: "http://localhost:8000"
  api_key: "YOUR_REFSERVER_API_KEY"
  
import_options:
  batch_size: 50
  delay_between_requests: 1.0
  skip_duplicates: true
  collections:
    - "Research Papers"
    - "Important Docs"
  exclude_tags:
    - "archived"
    - "draft"
```

**5.4 가져오기 리포트 생성**:
```python
# 가져오기 완료 후 상세 리포트 생성
def generate_import_report(results):
    report = {
        "timestamp": datetime.now().isoformat(),
        "total_items": len(results),
        "successful": sum(1 for r in results if r["success"]),
        "failed": sum(1 for r in results if not r["success"]),
        "skipped": sum(1 for r in results if r.get("skipped")),
        "errors": [r for r in results if not r["success"]],
        "processing_time": calculate_total_time()
    }
    
    with open(f"import_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json", 'w') as f:
        json.dump(report, f, indent=2)
```

#### **6. 구현 우선순위**

1. **필수 (Phase 1과 함께)**:
   - API 인증 추가
   - 기본적인 오류 처리
   - 중복 검사 로직

2. **중요 (Phase 2 초기)**:
   - 진행 상황 추적
   - Rate limiting 처리
   - Dry-run 모드

3. **선택 (Phase 2 후기)**:
   - 고급 필터링 옵션
   - 설정 파일 지원
   - 상세 리포트 생성
