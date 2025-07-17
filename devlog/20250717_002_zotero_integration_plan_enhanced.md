# Zotero 연동 기능 고도화 계획 (개선안 통합)

## 1. 개요

이 문서는 Zotero 라이브러리 연동 기능 구현을 위한 종합 계획입니다. 초기 계획에 안정성, 보안, 사용 편의성을 위한 개선 제안을 통합하여, 실제 운영 환경에 적합한 강력하고 안정적인 기능을 구현하는 것을 목표로 합니다.

---

## 2. Phase 1: 백엔드 API 고도화

**목표**: 사용자가 제공한 메타데이터를 안전하고 효율적으로 처리하며, 향후 확장성을 고려한 백엔드 API를 구현합니다.

### 2.1. 데이터베이스 모델 확장 (`app/models.py`)

**목적**: 사용자 제공 데이터와 자동 추출 데이터를 명확히 구분하고, Zotero와의 정확한 연동 및 중복 방지를 위한 기반을 마련합니다.

*   **`Metadata` 모델 수정**:
    *   `source` 필드를 추가하여 메타데이터의 출처를 기록합니다.
        ```python
        # app/models.py
        class Metadata(BaseModel):
            # ... 기존 필드 ...
            source = CharField(default='extracted', index=True) # 값: 'extracted', 'user_api'
        ```

*   **`ZoteroLink` 모델 신규 추가**:
    *   논문과 Zotero 아이템 간의 관계를 저장하여 정확한 중복 검사와 향후 동기화 기능을 지원합니다.
        ```python
        # app/models.py
        class ZoteroLink(BaseModel):
            paper = ForeignKeyField(Paper, backref='zotero_link', unique=True)
            zotero_key = CharField(unique=True, index=True)
            zotero_version = IntegerField()
            library_id = CharField()
            imported_at = DateTimeField(default=datetime.datetime.now)
        ```

### 2.2. 보안 강화된 API 엔드포인트 구현 (`app/main.py`)

**목적**: 인증 및 인가(Admin 권한)가 적용된 안전한 파일 업로드 API를 구현합니다.

*   **엔드포인트**: `POST /api/v1/papers/upload_with_metadata`
*   **주요 변경 사항**:
    *   FastAPI의 `Depends`를 사용하여 사용자 인증을 필수로 적용합니다.
    *   인증된 사용자가 관리자(`is_admin`)인지 확인하는 권한 검사 로직을 추가합니다.

    ```python
    # app/main.py 예시
    from app.auth import get_current_user # auth.py에 정의된 함수

    @router.post("/api/v1/papers/upload_with_metadata")
    async def upload_with_metadata(
        file: UploadFile = File(...),
        title: str = Form(...),
        authors: str = Form(...), # JSON string
        year: Optional[int] = Form(None),
        zotero_key: Optional[str] = Form(None), # Zotero 키 추가
        current_user: User = Depends(get_current_user) # 인증 추가
    ):
        if not current_user.is_admin:
            raise HTTPException(status_code=403, detail="Admin access required")
        
        # Zotero 키가 제공되면 ZoteroLink 객체 생성/업데이트
        # ... (구현 로직) ...
    ```

### 2.3. 처리 파이프라인 수정 (`app/pipeline.py`)

**목적**: 사용자가 API를 통해 제공한 메타데이터를 파이프라인이 덮어쓰지 않도록 보장합니다.

*   **대상 함수**: `_extract_metadata`
*   **변경 로직**: 함수 시작 시 `Metadata.source` 필드를 확인하여 `'user_api'`인 경우, 자동 추출 로직을 건너뜁니다. (기존 계획과 동일)

### 2.4. 후속 조치

*   모델 변경 사항을 데이터베이스에 적용하기 위해 터미널에서 `python migrate.py`를 실행하여 마이그레이션 스크립트를 생성하고, 서버 재시작 시 적용되도록 합니다.

---

## 3. Phase 2: Zotero 가져오기 스크립트 구현

**목표**: 대용량 라이브러리도 안정적으로 처리할 수 있으며, 사용자가 제어하기 쉬운 유연한 가져오기 스크립트를 작성합니다.

### 3.1. 의존성 추가 (`requirements.txt`)

*   `PyZotero`: Zotero API 연동
*   `requests`: RefServerLite API 호출
*   `PyYAML`: 설정 파일 처리

### 3.2. 설정 파일 도입 (`scripts/config.yml`)

**목적**: 민감 정보(API 키 등)와 설정을 코드에서 분리하여 관리합니다.

```yaml
# scripts/config.yml 예시
zotero:
  library_id: "YOUR_LIBRARY_ID"
  api_key: "YOUR_API_KEY"

refserver:
  api_url: "http://127.0.0.1:8000"
  # RefServerLite API 인증을 위한 사용자 정보
  username: "admin@example.com"
  password: "admin_password"

import_options:
  batch_size: 20
  delay_seconds: 1.5
  skip_existing: true
```

### 3.3. 스크립트 기능 명세 (`scripts/import_from_zotero.py`)

스크립트는 아래의 고급 기능들을 포함하여 구현합니다.

*   **커맨드라인 인자**: `argparse` 사용
    *   `--dry-run`: 실제 실행 없이 시뮬레이션만 수행
    *   `--collection`: 특정 컬렉션만 대상 지정
    *   `--since-version`: 특정 Zotero 버전 이후 변경된 항목만 대상 지정
    *   `--limit`: 가져올 최대 항목 수 지정

*   **인증 처리**: `config.yml`의 정보로 RefServerLite에 로그인하여 인증 토큰을 획득하고, 이후 모든 API 요청에 사용합니다.

*   **진행 상황 관리**: 중단 시 이어하기 지원
    *   처리가 완료된 Zotero 아이템 키를 `zotero_import_progress.json`과 같은 파일에 기록합니다.
    *   스크립트 재시작 시 이 파일을 읽어 이미 처리된 항목은 건너뜁니다.

*   **배치 처리 및 Rate Limiting**: Zotero API 제한 대응
    *   `config.yml`에 정의된 `batch_size` 만큼 아이템을 처리하고, `delay_seconds` 만큼 대기하여 API 호출 제한을 준수합니다.

*   **중복 문서 처리**: `ZoteroLink` 모델을 활용하여 스크립트 시작 시 RefServerLite DB에 이미 존재하는 Zotero 키 목록을 가져와 중복 추가를 방지합니다.

*   **안정적인 오류 처리**: 특정 논문 처리 중 오류가 발생해도 전체 스크립트가 중단되지 않도록 `try...except` 블록으로 각 아이템 처리를 감쌉니다. 실패한 항목은 리포트를 위해 기록합니다.

*   **상세 리포트 생성**: 스크립트 실행 완료 후, 성공/실패/건너뛴 항목 수, 오류 목록, 총 소요 시간 등을 담은 JSON 형식의 리포트 파일을 생성합니다.

---

## 4. 구현 우선순위

1.  **1순위 (핵심 기능)**:
    *   `Phase 1`의 모든 백엔드 API 및 모델 변경
    *   API 엔드포인트에 대한 인증/인가 적용
    *   Zotero 스크립트의 기본적인 연동 로직 (인증, 단일 아이템 가져오기)

2.  **2순위 (안정성 및 사용성)**:
    *   스크립트에 **중복 문서 처리** 및 **기본 오류 처리** 로직 추가
    *   **Dry-run 모드** 구현
    *   **배치 처리** 및 **Rate Limiting** 대응 로직 추가

3.  **3순위 (고급 기능)**:
    *   **진행 상황 관리**(이어하기) 기능 구현
    *   **설정 파일**(`config.yml`) 지원
    *   상세 **필터링 옵션** (컬렉션, 날짜 등) 구현
    *   실행 결과 **리포트 생성** 기능 구현
