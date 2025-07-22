# Zotero 통합 심화 및 PDF 중복 방지 기반 마련 계획

## 1. 개요

이 문서는 RefServerLite와 Zotero 라이브러리 간의 통합을 심화하고, PDF 파일의 내용 기반 중복 방지를 위한 기반을 마련하는 계획을 상세히 기술합니다. 목표는 사용자가 RefServerLite 내에서 Zotero 라이브러리를 직접 연결하고 동기화하며, 중복된 PDF 파일이 시스템에 저장되는 것을 효율적으로 관리하는 것입니다.

## 2. 목표

*   RefServerLite 사용자 계정에 Zotero Library ID 및 API 키를 연결합니다.
*   연결된 Zotero 라이브러리에서 컬렉션 및 아이템(논문, PDF 첨부파일 포함)을 가져와 RefServerLite와 동기화합니다.
*   동기화된 PDF 파일의 Zotero 고유 ID를 RefServerLite에 기록하여 추적성을 확보합니다.
*   새로 업로드되거나 동기화되는 PDF 파일에 대해 내용 기반(임베딩 기반) 중복 검사를 수행하고, 중복 발견 시 적절히 처리합니다.

## 3. 고수준 계획

1.  **Phase 1: 데이터베이스 스키마 확장**: 사용자 모델에 Zotero 연결 정보 필드를 추가합니다.
2.  **Phase 2: 백엔드 API 개발**: Zotero 계정 연결, 동기화 트리거, 중복 검사 API를 구현합니다.
3.  **Phase 3: Zotero 동기화 로직 구현**: 백그라운드에서 Zotero 라이브러리를 가져와 처리하는 로직을 개발합니다.
4.  **Phase 4: PDF 중복 방지 전략 구현**: 문서 임베딩을 활용한 중복 검사 및 처리 로직을 통합합니다.
5.  **Phase 5: 프론트엔드 UI 통합**: Zotero 설정 및 동기화 상태를 관리할 수 있는 UI를 제공합니다.

## 4. 상세 구현 계획

### Phase 1: 데이터베이스 스키마 확장

**목표**: RefServerLite 사용자 계정에 Zotero 연결 정보를 저장할 수 있도록 모델을 확장합니다.

*   **파일**: `app/models.py`
*   **변경 사항**:
    *   **`User` 모델 수정**: 
        *   `zotero_library_id = CharField(null=True)`: 사용자의 Zotero Library ID
        *   `zotero_api_key = CharField(null=True)`: 사용자의 Zotero API Key (보안 고려 필요)
        *   `zotero_last_sync = DateTimeField(null=True)`: 마지막 동기화 시간 기록

    *   **`ZoteroLink` 모델 (기존 활용)**: 이미 `zotero_key`, `library_id`, `zotero_version`, `collection_keys`, `tags` 등을 포함하고 있어 Zotero 아이템과의 연결에 충분합니다.

*   **후속 조치**: 모델 변경 후, `python migrate.py`를 실행하여 마이그레이션 스크립트를 생성하고 적용합니다.

### Phase 2: 백엔드 API 개발

**목표**: Zotero 계정 연결 및 동기화 트리거, 그리고 중복 검사를 위한 API 엔드포인트를 제공합니다.

*   **파일**: `app/main.py`

*   **신규 엔드포인트**: `POST /api/v1/users/me/zotero_config`
    *   **기능**: 현재 로그인한 사용자의 Zotero Library ID 및 API Key를 설정합니다.
    *   **인증**: 로그인된 사용자(`Depends(get_current_user)`)만 접근 가능합니다.
    *   **보안**: API Key는 안전하게 저장되어야 합니다 (예: 환경 변수, Vault 등. 현재는 DB에 저장하지만, 향후 보안 강화 필요성 명시).

*   **신규 엔드포인트**: `POST /api/v1/users/me/zotero_sync`
    *   **기능**: 현재 로그인한 사용자의 Zotero 라이브러리 동기화를 시작합니다.
    *   **로직**: 백그라운드 작업(`ProcessingJob`)을 생성하여 실제 동기화 로직을 비동기적으로 실행합니다.
    *   **인증**: 로그인된 사용자만 접근 가능합니다.

*   **신규 엔드포인트**: `GET /api/v1/documents/check_duplicate_embedding`
    *   **기능**: 주어진 임베딩 벡터와 유사한 기존 문서가 있는지 확인합니다.
    *   **요청**: `embedding` (JSON 배열 형태의 임베딩 벡터), `threshold` (유사도 임계값)
    *   **응답**: 유사한 문서 목록 (`doc_id`, `similarity_score`)
    *   **인증**: 관리자 권한(`Depends(get_current_user)`)이 필요합니다.

### Phase 3: Zotero 동기화 로직 구현

**목표**: Zotero 라이브러리에서 데이터를 가져와 RefServerLite에 통합하는 백그라운드 로직을 개발합니다.

*   **파일**: `app/pipeline.py` (또는 `app/zotero_sync.py` 신규 모듈)
*   **로직**: `ProcessingJob`의 새로운 타입(예: `job_type='zotero_sync'`)으로 백그라운드에서 실행됩니다.
    1.  **사용자 Zotero 설정 로드**: `User` 모델에서 `zotero_library_id`와 `zotero_api_key`를 가져옵니다.
    2.  **Zotero API 연결**: `pyzotero`를 사용하여 Zotero 라이브러리에 연결합니다.
    3.  **아이템 가져오기**: Zotero API의 `since` 파라미터를 활용하여 마지막 동기화 이후 변경된 아이템만 가져와 증분 동기화를 수행합니다.
    4.  **아이템 순회 및 처리**: 각 Zotero 아이템에 대해 다음을 수행합니다.
        *   **PDF 첨부파일 확인**: PDF 첨부파일이 있는 아이템만 대상으로 합니다.
        *   **기존 문서 확인**: `ZoteroLink` 모델을 통해 해당 Zotero 아이템이 RefServerLite에 이미 존재하는지 확인합니다.
        *   **중복 검사 (Phase 4와 연동)**: PDF 파일을 다운로드하기 전에, Zotero 아이템의 메타데이터(제목, 저자, 연도)를 기반으로 RefServerLite에 유사한 문서가 있는지 1차 검사합니다. (이후 PDF 다운로드 후 임베딩 기반 2차 검사)
        *   **PDF 다운로드**: Zotero에서 PDF 첨부파일을 다운로드합니다.
        *   **RefServerLite 업로드**: `upload_with_metadata` API (또는 내부 함수)를 호출하여 PDF와 메타데이터를 RefServerLite에 업로드합니다.
        *   **`ZoteroLink` 업데이트/생성**: 업로드 성공 후 `ZoteroLink` 레코드를 생성하거나 업데이트합니다.
    5.  **마지막 동기화 시간 업데이트**: 동기화 완료 후 `User.zotero_last_sync` 필드를 업데이트합니다.

### Phase 4: PDF 중복 방지 전략 구현

**목표**: 문서 임베딩을 활용하여 내용 기반의 PDF 중복을 식별하고 관리합니다.

*   **파일**: `app/pipeline.py` (또는 `app/main.py`의 `upload_with_metadata` 내부)
*   **로직**: 새로운 문서가 시스템에 추가될 때(업로드 또는 Zotero 동기화), 다음 단계를 수행합니다.
    1.  **문서 임베딩 생성**: 업로드된 PDF의 문서 레벨 임베딩을 생성합니다. (기존 파이프라인에서 이미 수행)
    2.  **유사 임베딩 검색**: `app.state.chroma_collection`을 사용하여 새로 생성된 임베딩과 유사한 기존 문서 임베딩을 검색합니다. `GET /api/v1/documents/check_duplicate_embedding` API를 내부적으로 활용할 수 있습니다.
    3.  **유사도 임계값**: 특정 유사도 임계값(예: 코사인 유사도 0.95 이상)을 초과하는 문서가 발견되면 잠재적 중복으로 간주합니다.
    4.  **중복 처리 정책**: 
        *   **경고 및 건너뛰기**: 사용자에게 중복 가능성을 알리고 업로드를 중단합니다. (초기 구현에 적합)
        *   **기존 문서에 연결**: 새로 업로드된 문서를 기존 중복 문서에 연결하는 필드(`is_duplicate_of = ForeignKeyField(Paper, null=True)`)를 `Paper` 모델에 추가하여, 여러 버전의 동일 문서를 관리할 수 있도록 합니다.
        *   **사용자 선택**: 중복 발견 시 사용자에게 건너뛸지, 새 버전으로 추가할지, 기존 문서를 대체할지 선택권을 제공합니다.

### Phase 5: 프론트엔드 UI 통합

**목표**: Zotero 계정 설정 및 동기화 상태를 관리할 수 있는 사용자 인터페이스를 제공합니다.

*   **파일**: `app/templates/admin.html` (또는 `app/templates/settings.html` 신규 파일)
*   **UI 요소**:
    *   **Zotero 설정 섹션**: 
        *   Zotero Library ID 및 API Key를 입력하고 저장하는 폼.
        *   현재 연결된 Zotero 계정 정보 표시.
    *   **동기화 버튼**: Zotero 동기화를 시작하는 버튼 (`POST /api/v1/users/me/zotero_sync` 호출).
    *   **동기화 상태 표시**: `ProcessingJob` 모니터링 대시보드와 연동하여 Zotero 동기화 작업의 진행 상태를 표시합니다.
    *   **중복 문서 관리**: (향후 확장) 중복으로 식별된 문서를 관리하고 해결할 수 있는 UI (예: 병합, 삭제, 연결 해제).

## 5. 고려 사항 및 향후 개선 방향

*   **Zotero API Key 보안**: `User` 모델에 API Key를 직접 저장하는 것은 보안상 취약할 수 있습니다. 향후 환경 변수, HashiCorp Vault, AWS Secrets Manager 등 더 안전한 비밀 관리 솔루션 도입을 고려해야 합니다.
*   **동기화 전략**: 증분 동기화의 효율성을 높이기 위해 Zotero의 `lastModifiedVersion`을 활용하고, RefServerLite의 `ZoteroLink.zotero_version`과 비교하여 변경된 아이템만 처리합니다.
*   **오류 처리**: Zotero API 호출 실패, PDF 다운로드 실패, 중복 처리 실패 등 다양한 오류 상황에 대한 견고한 로깅 및 사용자 피드백 메커니즘을 구현합니다.
*   **성능**: 대규모 Zotero 라이브러리 동기화 시 성능 병목 현상(특히 PDF 다운로드 및 임베딩 생성)을 모니터링하고 최적화합니다.
*   **사용자 경험**: 중복 문서 처리 시 사용자에게 명확하고 직관적인 선택지를 제공하는 UI/UX 설계가 중요합니다.

## 6. 구현 우선순위

1.  **1순위**: `User` 모델에 Zotero 연결 필드 추가 및 마이그레이션.
2.  **2순위**: `POST /api/v1/users/me/zotero_config` 및 `POST /api/v1/users/me/zotero_sync` API 엔드포인트 구현.
3.  **3순위**: `ProcessingJob`을 활용한 Zotero 동기화 백그라운드 로직의 기본 구현 (증분 동기화 및 중복 검사 제외).
4.  **4순위**: `GET /api/v1/documents/check_duplicate_embedding` API 구현 및 `upload_with_metadata`에 임베딩 기반 중복 검사 로직 통합 (경고/건너뛰기 정책).
5.  **5순위**: Zotero 설정 및 동기화 트리거를 위한 프론트엔드 UI 구현.
6.  **6순위**: Zotero 동기화 로직에 증분 동기화 및 상세 중복 처리 정책(연결) 추가.

## 7. 개선 제안 및 확장 계획

### 7.1 보안 강화

**현재 제안의 문제점**:
```python
# 현재 제안
zotero_api_key = CharField(null=True)  # DB에 직접 저장 - 보안 취약
```

**개선 방안**:
```python
# 1. 환경 변수 기반 암호화 키 사용
from cryptography.fernet import Fernet
import os

class User(BaseModel):
    zotero_library_id = CharField(null=True)
    zotero_api_key_encrypted = CharField(null=True)  # 암호화된 키 저장
    
    def set_zotero_api_key(self, api_key):
        cipher_suite = Fernet(os.getenv('ENCRYPTION_KEY'))
        self.zotero_api_key_encrypted = cipher_suite.encrypt(api_key.encode()).decode()
    
    def get_zotero_api_key(self):
        if not self.zotero_api_key_encrypted:
            return None
        cipher_suite = Fernet(os.getenv('ENCRYPTION_KEY'))
        return cipher_suite.decrypt(self.zotero_api_key_encrypted.encode()).decode()

# 2. 토큰 기반 인증 고려
class ZoteroToken(BaseModel):
    user = ForeignKeyField(User, backref='zotero_tokens')
    access_token = CharField()
    refresh_token = CharField(null=True)
    expires_at = DateTimeField()
    created_at = DateTimeField(default=datetime.datetime.now)
```

### 7.2 동기화 성능 최적화

**성능 병목 지점**:
- 대규모 라이브러리 (수천 개 문서) 동기화
- PDF 다운로드 및 임베딩 생성 시간
- 네트워크 I/O 대기 시간

**개선 방안**:
```python
# 1. 동적 배치 크기 조절
class SyncConfig:
    initial_batch_size = 10
    max_batch_size = 50
    batch_size_increment = 5
    performance_threshold = 30  # 초당 처리 속도

# 2. 우선순위 기반 동기화
class SyncPriority(Enum):
    RECENT = "recent"        # 최근 수정된 문서 우선
    IMPORTANT = "important"  # 중요 컬렉션 우선  
    MISSING = "missing"      # 누락된 PDF 우선

# 3. 동기화 모니터링
class SyncMetrics(BaseModel):
    sync_session_id = CharField(primary_key=True)
    user = ForeignKeyField(User)
    started_at = DateTimeField()
    completed_at = DateTimeField(null=True)
    total_items = IntegerField()
    processed_items = IntegerField(default=0)
    success_count = IntegerField(default=0)
    error_count = IntegerField(default=0)
    avg_processing_time = FloatField(null=True)
```

### 7.3 중복 처리 정책 확장

**현재 제안의 한계**:
- 단순한 경고/건너뛰기 정책만 제공
- 사용자 선택권 부족

**개선 방안**:
```python
# 1. 다양한 중복 처리 액션
class DuplicateAction(Enum):
    SKIP = "skip"                    # 건너뛰기
    MERGE_METADATA = "merge_metadata"  # 메타데이터만 병합
    NEW_VERSION = "new_version"      # 새 버전으로 추가
    REPLACE = "replace"              # 기존 문서 대체
    ASK_USER = "ask_user"            # 사용자에게 묻기

# 2. 사용자별 중복 처리 설정
class UserDuplicatePolicy(BaseModel):
    user = ForeignKeyField(User)
    similarity_threshold = FloatField(default=0.95)
    default_action = CharField(default="ask_user")
    auto_merge_same_zotero_key = BooleanField(default=True)
    
# 3. 중복 문서 관리 모델 확장
class Paper(BaseModel):
    # ... 기존 필드들 ...
    is_duplicate_of = ForeignKeyField('self', null=True, backref='duplicates')
    duplicate_confidence = FloatField(null=True)  # 중복 확신도
    duplicate_reason = CharField(null=True)       # 중복 판단 근거
```

### 7.4 사용자 경험 개선

**동기화 정책 다양화**:
```python
class UserSyncPolicy(BaseModel):
    user = ForeignKeyField(User)
    auto_sync_enabled = BooleanField(default=False)
    auto_sync_interval = IntegerField(default=24)  # 시간 단위
    sync_collections = JSONField(default=list)     # 특정 컬렉션만
    sync_tags = JSONField(default=list)            # 특정 태그만
    exclude_collections = JSONField(default=list)  # 제외할 컬렉션
    max_file_size_mb = IntegerField(default=50)    # 최대 파일 크기
    sync_attachments_only = BooleanField(default=True)  # PDF 첨부파일만
```

**사용자 대시보드 구성**:
```python
# API 엔드포인트 확장
GET /api/v1/users/me/zotero_status        # 연결 상태 및 통계
GET /api/v1/users/me/sync_history         # 동기화 이력
GET /api/v1/users/me/duplicate_documents  # 중복 문서 목록
POST /api/v1/users/me/resolve_duplicate   # 중복 문서 해결
```

### 7.5 양방향 동기화 (선택사항)

**RefServerLite → Zotero 내보내기**:
```python
# 1. 메타데이터 수정사항 Zotero로 전송
POST /api/v1/users/me/zotero_export/{doc_id}

# 2. 새로운 문서를 Zotero에 추가
POST /api/v1/users/me/zotero_create_item

# 3. 태그 및 컬렉션 동기화
POST /api/v1/users/me/zotero_sync_tags
POST /api/v1/users/me/zotero_sync_collections
```

### 7.6 고급 중복 검사 알고리즘

**현재 제안의 한계**:
- 단순 코사인 유사도만 사용
- 메타데이터 정보 미활용

**개선 방안**:
```python
class DuplicateDetector:
    def __init__(self):
        self.embedding_weight = 0.7
        self.metadata_weight = 0.3
        
    def calculate_similarity(self, doc1, doc2):
        # 1. 임베딩 유사도
        embedding_sim = cosine_similarity(doc1.embedding, doc2.embedding)
        
        # 2. 메타데이터 유사도
        metadata_sim = self.calculate_metadata_similarity(doc1, doc2)
        
        # 3. 가중 평균
        return (embedding_sim * self.embedding_weight + 
                metadata_sim * self.metadata_weight)
    
    def calculate_metadata_similarity(self, doc1, doc2):
        # 제목, 저자, 발행연도 유사도 계산
        title_sim = self.text_similarity(doc1.title, doc2.title)
        author_sim = self.author_similarity(doc1.authors, doc2.authors)
        year_sim = 1.0 if doc1.year == doc2.year else 0.0
        
        return (title_sim * 0.5 + author_sim * 0.3 + year_sim * 0.2)
```

### 7.7 구현 타임라인 제안

**즉시 구현 가능 (1-2주)**:
1. User 모델 확장 및 기본 API 구현
2. 암호화된 API 키 저장 구현
3. Admin 페이지에 Zotero 설정 UI 추가

**단기 목표 (2-4주)**:
4. 백그라운드 동기화 로직 구현
5. 기본 중복 검사 API 구현
6. 동기화 진행률 모니터링

**중기 목표 (1-2개월)**:
7. 고급 중복 처리 정책 구현
8. 사용자 대시보드 및 통계 제공
9. 증분 동기화 최적화

**장기 목표 (2-3개월)**:
10. 양방향 동기화 구현
11. 고급 중복 검사 알고리즘 적용
12. 성능 최적화 및 대규모 라이브러리 지원

### 7.8 결론

이 확장 계획은 **기존 계획의 실용적 기반을 유지하면서 사용자 경험과 시스템 견고성을 크게 향상**시킬 수 있습니다. 특히:

- **보안 강화**: 암호화된 API 키 저장으로 보안 리스크 최소화
- **성능 최적화**: 대규모 라이브러리 동기화 시 실용적 성능 확보
- **사용자 경험**: 유연한 중복 처리 정책과 직관적 대시보드
- **차별화**: 임베딩 기반 고급 중복 검사로 경쟁력 확보

**추천 접근법**: 기본 기능부터 구현하여 사용자 피드백을 받은 후, 점진적으로 고급 기능을 추가하는 것이 가장 효과적일 것입니다.
