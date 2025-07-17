# Zotero 연동 기능 구현 완료

## 구현 개요

2025년 1월 17일, RefServerLite에 Zotero 라이브러리와의 연동 기능을 성공적으로 구현했습니다. 이 기능을 통해 사용자는 Zotero에 저장된 논문 PDF와 메타데이터를 RefServerLite로 일괄 가져올 수 있습니다.

## 주요 구현 내용

### 1. 데이터베이스 모델 확장

#### Metadata 모델 수정 (`app/models.py`)
- `source` 필드 추가: 메타데이터 출처 구분 (`'extracted'` 또는 `'user_api'`)
- 사용자 제공 메타데이터와 자동 추출 메타데이터를 명확히 구분

#### ZoteroLink 모델 신규 추가 (`app/models.py`)
```python
class ZoteroLink(BaseModel):
    paper = ForeignKeyField(Paper, backref='zotero_link', unique=True)
    zotero_key = CharField(unique=True, index=True)
    zotero_version = IntegerField()
    library_id = CharField()
    collection_keys = TextField(null=True)  # JSON array
    tags = TextField(null=True)  # JSON array
    imported_at = DateTimeField(default=datetime.datetime.now)
```

### 2. 보안 강화된 API 엔드포인트

#### `/api/v1/papers/upload_with_metadata` (`app/main.py`)
- **인증 필수**: Bearer 토큰 기반 인증
- **권한 검사**: 관리자 권한 필요
- **중복 검사**: Zotero key 기반 중복 방지
- **메타데이터 처리**: 사용자 제공 메타데이터 우선 적용

주요 파라미터:
- `file`: PDF 파일 (multipart/form-data)
- `title`: 논문 제목
- `authors`: 저자 목록 (JSON 문자열)
- `year`: 출판 연도
- `zotero_key`: Zotero 아이템 키 (선택)
- `zotero_library_id`: Zotero 라이브러리 ID (선택)

### 3. 처리 파이프라인 개선

#### 메타데이터 추출 로직 수정 (`app/pipeline.py`)
```python
# 사용자 제공 메타데이터 확인
existing_metadata = paper.metadata.get()
if existing_metadata.source == 'user_api':
    logger.info(f"Skipping metadata extraction - user-provided metadata exists")
    return
```

### 4. Zotero 가져오기 스크립트

#### `scripts/import_from_zotero.py`
완전한 기능을 갖춘 가져오기 스크립트 구현:

**핵심 기능:**
- RefServerLite API 인증 처리
- Zotero 라이브러리에서 PDF 첨부파일이 있는 아이템 검색
- 메타데이터 추출 및 포맷팅
- PDF 다운로드 및 업로드
- 진행 상황 추적 (중단 후 재개 가능)
- 배치 처리 및 Rate Limiting 대응
- 상세 리포트 생성

**명령줄 옵션:**
```bash
# 기본 가져오기
python import_from_zotero.py

# 시뮬레이션 (실제 가져오기 없음)
python import_from_zotero.py --dry-run

# 특정 컬렉션만 가져오기
python import_from_zotero.py --collection COLLECTION_ID

# 최근 변경사항만 가져오기
python import_from_zotero.py --since-version 12345

# 개수 제한
python import_from_zotero.py --limit 10
```

### 5. 설정 파일 템플릿

#### `scripts/config.yml.example`
```yaml
zotero:
  library_id: "YOUR_LIBRARY_ID"
  api_key: "YOUR_API_KEY"

refserver:
  api_url: "http://localhost:8000"
  username: "admin"
  password: "admin123"

import_options:
  batch_size: 20
  delay_seconds: 1.5
  skip_existing: true
```

### 6. 의존성 추가

#### `requirements.txt`
```
pyzotero==1.5.18
PyYAML==6.0.1
```

## 보안 및 안정성 특징

1. **인증 및 권한**
   - API 엔드포인트에 Bearer 토큰 인증 필수
   - 관리자 권한만 업로드 가능

2. **중복 방지**
   - Zotero key 기반 중복 검사
   - 이미 가져온 아이템 자동 건너뛰기

3. **오류 처리**
   - 개별 아이템 실패가 전체 프로세스를 중단시키지 않음
   - 상세한 오류 로깅 및 리포트

4. **진행 상황 관리**
   - 중단된 가져오기 재개 가능
   - JSON 파일로 진행 상황 저장

## 사용 시나리오

1. **초기 라이브러리 마이그레이션**
   ```bash
   # 전체 Zotero 라이브러리를 RefServerLite로 가져오기
   python import_from_zotero.py
   ```

2. **정기적 동기화**
   ```bash
   # 마지막 동기화 이후 변경사항만 가져오기
   python import_from_zotero.py --since-version 45678
   ```

3. **특정 프로젝트 가져오기**
   ```bash
   # 특정 컬렉션의 논문만 가져오기
   python import_from_zotero.py --collection "Research_Project_2025"
   ```

## 향후 개선 가능 사항

1. **양방향 동기화**: RefServerLite의 변경사항을 Zotero로 역동기화
2. **실시간 동기화**: Webhook 기반 자동 동기화
3. **Web UI 통합**: 관리자 대시보드에서 직접 가져오기 실행
4. **선택적 메타데이터 업데이트**: 기존 문서의 메타데이터만 업데이트하는 옵션

## 결론

이번 구현으로 RefServerLite는 Zotero와의 원활한 통합을 지원하게 되었습니다. 보안, 안정성, 사용성을 모두 고려한 프로덕션 레벨의 구현으로, 연구자들이 기존 Zotero 라이브러리를 RefServerLite의 고급 기능(OCR, 시맨틱 청킹, 임베딩 기반 검색)과 함께 활용할 수 있게 되었습니다.