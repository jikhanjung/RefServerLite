# Zotero 통합 심화 및 PDF 중복 방지 기반 마련 계획 (개정판)

## 1. 개요

이 문서는 RefServerLite와 Zotero 라이브러리 간의 통합을 심화하고, PDF 파일의 내용 기반 중복 방지를 위한 기반을 마련하는 개정된 계획을 상세히 기술합니다. 기존 계획에 보안 강화, 성능 최적화, 확장된 중복 처리 정책, 그리고 사용자 경험 개선 방안을 통합하여, 더욱 견고하고 지능적인 문서 관리 시스템을 구축하는 것을 목표로 합니다.

## 2. 목표

*   RefServerLite 사용자 계정에 Zotero Library ID 및 API 키를 안전하게 연결합니다.
*   연결된 Zotero 라이브러리에서 컬렉션 및 아이템(논문, PDF 첨부파일 포함)을 효율적으로 가져와 RefServerLite와 동기화합니다.
*   동기화된 PDF 파일의 Zotero 고유 ID를 RefServerLite에 기록하여 추적성을 확보합니다.
*   새로 업로드되거나 동기화되는 PDF 파일에 대해 내용 기반(임베딩 기반) 중복 검사를 수행하고, 사용자 설정에 따라 적절히 처리합니다.
*   사용자가 Zotero 통합 기능을 쉽게 설정하고 동기화 상태를 모니터링할 수 있는 직관적인 UI를 제공합니다.

## 3. 고수준 계획

이 계획은 다음의 주요 단계로 진행됩니다. 각 단계는 이전 단계의 결과물을 기반으로 점진적으로 기능을 확장합니다.

1.  **Phase 1: 핵심 데이터 모델 및 API 기반 구축**: Zotero 연결 정보 저장 및 기본 API 엔드포인트 구현.
2.  **Phase 2: Zotero 동기화 로직 구현**: 백그라운드에서 Zotero 라이브러리를 가져와 처리하는 로직 개발.
3.  **Phase 3: PDF 중복 방지 및 처리**: 문서 임베딩을 활용한 중복 검사 및 다양한 처리 정책 구현.
4.  **Phase 4: 사용자 인터페이스 통합**: Zotero 설정 및 동기화 상태를 관리할 수 있는 UI 제공.
5.  **Phase 5: 고급 기능 및 최적화**: 양방향 동기화, 고급 중복 검사 알고리즘, 성능 최적화 등.

## 4. 상세 구현 계획

### 4.1. Phase 1: 핵심 데이터 모델 및 API 기반 구축

**목표**: RefServerLite 사용자 계정에 Zotero 연결 정보를 안전하게 저장하고, 이를 위한 기본 API를 제공합니다.

*   **파일**: `app/models.py`, `app/main.py`
*   **변경 사항**:
    *   **`User` 모델 수정**: 
        *   `zotero_library_id = CharField(null=True)`: 사용자의 Zotero Library ID
        *   `zotero_api_key_encrypted = CharField(null=True)`: **암호화된 Zotero API Key 저장** (보안 강화)
        *   `zotero_last_sync = DateTimeField(null=True)`: 마지막 동기화 시간 기록
    *   **`ZoteroLink` 모델 (기존 활용)**: Zotero 아이템과의 연결에 사용.
    *   **`User` 모델에 API Key 암호화/복호화 메서드 추가**: `Fernet`을 활용하여 `zotero_api_key_encrypted` 필드를 관리합니다. `ENCRYPTION_KEY`는 환경 변수로 관리합니다.

*   **신규 엔드포인트**: `POST /api/v1/users/me/zotero_config`
    *   **기능**: 현재 로그인한 사용자의 Zotero Library ID 및 API Key를 설정합니다.
    *   **인증**: 로그인된 사용자(`Depends(get_current_user)`)만 접근 가능합니다.
    *   **보안**: API Key는 DB에 저장하기 전에 암호화합니다.

*   **신규 엔드포인트**: `POST /api/v1/users/me/zotero_sync`
    *   **기능**: 현재 로그인한 사용자의 Zotero 라이브러리 동기화를 시작합니다.
    *   **로직**: 백그라운드 작업(`ProcessingJob`)을 생성하여 실제 동기화 로직을 비동기적으로 실행합니다.
    *   **인증**: 로그인된 사용자만 접근 가능합니다.

*   **후속 조치**: 모델 변경 후, `python migrate.py`를 실행하여 마이그레이션 스크립트를 생성하고 적용합니다.

### 4.2. Phase 2: Zotero 동기화 로직 구현

**목표**: Zotero 라이브러리에서 데이터를 가져와 RefServerLite에 통합하는 백그라운드 로직을 개발합니다. 증분 동기화 및 성능 최적화를 고려합니다.

*   **파일**: `app/pipeline.py` (또는 `app/zotero_sync.py` 신규 모듈)
*   **로직**: `ProcessingJob`의 새로운 타입(예: `job_type='zotero_sync'`)으로 백그라운드에서 실행됩니다.
    1.  **사용자 Zotero 설정 로드**: `User` 모델에서 `zotero_library_id`와 **복호화된 `zotero_api_key`**를 가져옵니다.
    2.  **Zotero API 연결**: `pyzotero`를 사용하여 Zotero 라이브러리에 연결합니다.
    3.  **증분 동기화**: Zotero API의 `since` 파라미터를 활용하여 `User.zotero_last_sync` 이후 변경된 아이템만 가져와 처리합니다.
    4.  **아이템 순회 및 처리**: 각 Zotero 아이템에 대해 다음을 수행합니다.
        *   **PDF 첨부파일 확인**: PDF 첨부파일이 있는 아이템만 대상으로 합니다.
        *   **기존 문서 확인**: `ZoteroLink` 모델을 통해 해당 Zotero 아이템이 RefServerLite에 이미 존재하는지 확인합니다.
        *   **PDF 다운로드**: Zotero에서 PDF 첨부파일을 다운로드합니다.
        *   **RefServerLite 업로드**: `upload_with_metadata` API (또는 내부 함수)를 호출하여 PDF와 메타데이터를 RefServerLite에 업로드합니다.
        *   **`ZoteroLink` 업데이트/생성**: 업로드 성공 후 `ZoteroLink` 레코드를 생성하거나 업데이트합니다.
    5.  **마지막 동기화 시간 업데이트**: 동기화 완료 후 `User.zotero_last_sync` 필드를 업데이트합니다.

*   **성능 최적화 방안**: 
    *   **동적 배치 크기 조절**: Zotero API 호출 시 `batch_size`를 동적으로 조절하여 Rate Limit에 유연하게 대응합니다.
    *   **우선순위 기반 동기화**: (향후) `RECENT`, `IMPORTANT`, `MISSING` 등 우선순위를 두어 중요한 문서부터 처리합니다.
    *   **동기화 모니터링**: `SyncMetrics` 모델을 도입하여 동기화 세션별 통계(처리된 항목 수, 성공/실패, 평균 처리 시간)를 기록합니다.

### 4.3. Phase 3: PDF 중복 방지 및 처리

**목표**: 문서 임베딩을 활용하여 내용 기반의 PDF 중복을 식별하고, 사용자 설정에 따라 다양한 정책으로 처리합니다.

*   **파일**: `app/main.py` (`upload_with_metadata` 내부), `app/pipeline.py`
*   **신규 엔드포인트**: `GET /api/v1/documents/check_duplicate_embedding`
    *   **기능**: 주어진 임베딩 벡터와 유사한 기존 문서가 있는지 확인합니다.
    *   **요청**: `embedding` (JSON 배열 형태의 임베딩 벡터), `threshold` (유사도 임계값)
    *   **응답**: 유사한 문서 목록 (`doc_id`, `similarity_score`)
    *   **인증**: 관리자 권한(`Depends(get_current_user)`)이 필요합니다.

*   **로직**: 새로운 문서가 시스템에 추가될 때(업로드 또는 Zotero 동기화), 다음 단계를 수행합니다.
    1.  **문서 임베딩 생성**: 업로드된 PDF의 문서 레벨 임베딩을 생성합니다. (기존 파이프라인에서 이미 수행)
    2.  **유사 임베딩 검색**: `app.state.chroma_collection`을 사용하여 새로 생성된 임베딩과 유사한 기존 문서 임베딩을 검색합니다. `GET /api/v1/documents/check_duplicate_embedding` API를 내부적으로 활용할 수 있습니다.
    3.  **유사도 임계값**: 특정 유사도 임계값(예: 코사인 유사도 0.95 이상)을 초과하는 문서가 발견되면 잠재적 중복으로 간주합니다.
    4.  **중복 처리 정책 (확장)**: 
        *   **`Paper` 모델 확장**: `is_duplicate_of = ForeignKeyField('self', null=True, backref='duplicates')`, `duplicate_confidence = FloatField(null=True)`, `duplicate_reason = CharField(null=True)` 필드를 추가하여 중복 문서 간의 연결 및 상세 정보를 기록합니다.
        *   **다양한 액션**: `SKIP`, `MERGE_METADATA`, `NEW_VERSION`, `REPLACE`, `ASK_USER` 등 다양한 중복 처리 액션을 지원합니다.
        *   **사용자별 정책 설정**: `UserDuplicatePolicy` 모델을 도입하여 사용자별 기본 유사도 임계값 및 중복 처리 정책을 설정할 수 있도록 합니다.

*   **고급 중복 검사 알고리즘 (향후)**: 단순 코사인 유사도 외에 메타데이터(제목, 저자, 연도) 유사도를 결합하여 중복 판단의 정확도를 높이는 `DuplicateDetector` 클래스를 구현합니다.

### 4.4. Phase 4: 사용자 인터페이스 통합

**목표**: Zotero 계정 설정 및 동기화 상태를 관리할 수 있는 사용자 인터페이스를 제공합니다.

*   **파일**: `app/templates/admin.html` (또는 `app/templates/settings.html` 신규 파일)
*   **UI 요소**:
    *   **Zotero 설정 섹션**: 
        *   Zotero Library ID 및 API Key를 입력하고 저장하는 폼.
        *   현재 연결된 Zotero 계정 정보 표시.
    *   **동기화 버튼**: Zotero 동기화를 시작하는 버튼 (`POST /api/v1/users/me/zotero_sync` 호출).
    *   **동기화 상태 표시**: `ProcessingJob` 모니터링 대시보드와 `SyncMetrics`를 연동하여 Zotero 동기화 작업의 진행 상태 및 통계를 표시합니다.
    *   **중복 문서 관리**: (향후 확장) 중복으로 식별된 문서를 관리하고 해결할 수 있는 UI (예: 병합, 삭제, 연결 해제).
    *   **동기화 정책 설정**: `UserSyncPolicy` 모델을 통해 자동 동기화, 동기화 주기, 특정 컬렉션/태그 동기화, 최대 파일 크기 등 사용자별 동기화 정책을 설정하는 UI를 제공합니다.

### 4.5. Phase 5: 고급 기능 및 최적화

**목표**: 시스템의 장기적인 확장성과 사용자 경험을 위한 고급 기능을 구현하고 최적화를 진행합니다.

*   **양방향 동기화 (선택 사항)**: RefServerLite에서 변경된 메타데이터를 Zotero로 내보내거나, RefServerLite에서 생성된 문서를 Zotero에 추가하는 기능을 구현합니다.
*   **고급 중복 검사 알고리즘**: `DuplicateDetector`를 활용하여 임베딩 유사도와 메타데이터 유사도를 결합한 복합적인 중복 검사를 수행합니다.
*   **성능 최적화**: 대규모 라이브러리 동기화 시 발생할 수 있는 병목 현상을 지속적으로 모니터링하고 최적화합니다.
*   **Zotero API Key 보안 강화**: `User` 모델에 API Key를 직접 저장하는 방식에서 벗어나, 환경 변수, Vault 등 더 안전한 비밀 관리 솔루션 도입을 고려합니다.

## 5. 구현 우선순위 및 타임라인

이 계획은 다음의 우선순위에 따라 점진적으로 구현됩니다.

### 5.1. 즉시 구현 가능 (1-2주)
1.  **`User` 모델 확장**: `zotero_library_id`, `zotero_api_key_encrypted`, `zotero_last_sync` 필드 추가 및 마이그레이션.
2.  **API Key 암호화/복호화 로직 구현**: `User` 모델 내 메서드 및 관련 유틸리티 함수.
3.  **`POST /api/v1/users/me/zotero_config` API 구현**: Zotero 연결 정보 설정.
4.  **`POST /api/v1/users/me/zotero_sync` API 구현**: Zotero 동기화 백그라운드 작업 트리거.
5.  **Admin 페이지에 Zotero 설정 UI 추가**: 기본 설정 폼 및 연결 상태 표시.

### 5.2. 단기 목표 (2-4주)
1.  **Zotero 동기화 백그라운드 로직 구현**: `ProcessingJob`을 활용하여 Zotero 아이템 가져오기, PDF 다운로드, RefServerLite 업로드 (`upload_with_metadata` 재사용), `ZoteroLink` 생성/업데이트.
2.  **기본 중복 검사 API 구현**: `GET /api/v1/documents/check_duplicate_embedding`.
3.  **`upload_with_metadata`에 임베딩 기반 중복 검사 통합**: 중복 발견 시 경고 및 건너뛰기 정책 적용.
4.  **동기화 진행률 모니터링**: `ProcessingJob` 대시보드에 Zotero 동기화 작업 상태 표시.

### 5.3. 중기 목표 (1-2개월)
1.  **고급 중복 처리 정책 구현**: `Paper` 모델 확장 및 `UserDuplicatePolicy` 모델 도입, 다양한 중복 처리 액션 지원.
2.  **사용자 대시보드 및 통계 제공**: Zotero 연결 상태, 동기화 이력, 중복 문서 목록 등을 보여주는 UI 확장.
3.  **증분 동기화 최적화**: Zotero `lastModifiedVersion` 및 `User.zotero_last_sync`를 활용한 효율적인 동기화.
4.  **동기화 성능 최적화**: 동적 배치 크기 조절, 우선순위 기반 동기화 (선택 사항).

### 5.4. 장기 목표 (2-3개월)
1.  **양방향 동기화 구현**: RefServerLite에서 Zotero로 메타데이터 내보내기 및 새 아이템 추가.
2.  **고급 중복 검사 알고리즘 적용**: 임베딩과 메타데이터를 결합한 `DuplicateDetector` 구현.
3.  **성능 최적화 및 대규모 라이브러리 지원**: 지속적인 모니터링 및 최적화.
4.  **Zotero API Key 보안 강화**: 환경 변수, Vault 등 더 안전한 비밀 관리 솔루션 도입.

## 6. 결론

이 개정된 계획은 RefServerLite의 Zotero 통합 기능을 단순한 가져오기 도구를 넘어, **보안, 성능, 사용자 경험, 그리고 지능적인 중복 관리를 아우르는 강력한 문서 관리 시스템**으로 발전시키기 위한 로드맵입니다. 단계별 접근 방식을 통해 안정적으로 기능을 확장하고, 사용자에게 더욱 가치 있는 경험을 제공할 수 있을 것으로 기대합니다.
