# 제목: 시스템 반응성 향상을 위한 CPU 집약적 작업 비동기 전환 계획

**날짜:** 2025-07-24

### 1. 목표

- OCR, 임베딩, 시각화 등 CPU를 많이 사용하는 동기식(blocking) 작업들을 별도의 스레드에서 실행하여 FastAPI의 메인 이벤트 루프가 멈추는 현상을 방지합니다.
- 사용자가 PDF를 업로드하거나 다른 무거운 작업을 요청했을 때도, 다른 모든 API가 지연 없이 즉시 응답하도록 보장합니다.
- `ThreadPoolExecutor`를 활용하여 최소한의 코드 변경으로 최대한의 반응성 향상을 이끌어 냅니다.

### 2. 단계별 실행 계획

#### Phase 0: 사전 준비 - 재사용 가능한 헬퍼(Helper) 함수 생성

모든 곳에서 `asyncio.get_event_loop().run_in_executor(...)`를 반복적으로 작성하는 대신, 이를 캡슐화한 재사용 가능한 헬퍼 함수를 만듭니다. 이는 코드의 가독성과 유지보수성을 크게 향상시킵니다.

1.  **`app/utils.py` 파일 생성 (또는 기존 파일 활용):**
    프로젝트에 `app/utils.py` 파일이 없다면 새로 생성합니다.

2.  **비동기 실행 헬퍼 함수 추가:**
    `app/utils.py`에 다음 함수를 추가합니다.

    ```python
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    from typing import Callable, Any

    # 프로젝트 전역에서 사용할 스레드 풀 실행기
    # CPU 코어 수에 맞춰 적절한 worker 수를 설정할 수 있습니다.
    executor = ThreadPoolExecutor()

    async def run_sync_in_executor(sync_fn: Callable, *args: Any) -> Any:
        """
        동기 함수를 별도의 스레드에서 실행하여 이벤트 루프 블로킹을 방지합니다.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(executor, sync_fn, *args)
    ```

#### Phase 1: 핵심 처리 파이프라인 전환 (`app/pipeline.py`)

가장 중요하고 무거운 작업들이 모여있는 PDF 처리 파이프라인을 최우선으로 전환합니다.

1.  **`app/pipeline.py`의 `process_pdf_file` 함수를 `async`로 변경:**
    - 기존 `def process_pdf_file(...)`을 `async def process_pdf_file(...)`로 수정합니다.

2.  **함수 내 동기식 호출들을 `await run_sync_in_executor`로 감싸기:**
    - **OCR:** `extract_text_from_pdf` 호출 부분을 수정합니다.
      ```python
      # 변경 전
      # text = extract_text_from_pdf(pdf_path, doc.id)

      # 변경 후
      from .utils import run_sync_in_executor
      from .ocr import extract_text_from_pdf

      text = await run_sync_in_executor(extract_text_from_pdf, pdf_path, doc.id)
      ```
    - **메타데이터 추출:** `extract_metadata_from_text` 호출 부분을 수정합니다.
      ```python
      # 변경 전
      # metadata = extract_metadata_from_text(text)

      # 변경 후
      from .metadata import extract_metadata_from_text

      metadata = await run_sync_in_executor(extract_metadata_from_text, text)
      ```
    - **임베딩 생성:** `get_embedding` (또는 관련 함수) 호출 부분을 수정합니다.
      ```python
      # 변경 전
      # embedding = get_embedding(text_for_embedding, model_name)

      # 변경 후
      from .embedding import get_embedding

      embedding = await run_sync_in_executor(get_embedding, text_for_embedding, model_name)
      ```

3.  **`process_pdf_file`을 호출하는 부분 수정:**
    - `app/main.py` 등에서 `process_pdf_file`을 호출하는 부분이 있다면, `BackgroundTasks`에 추가하는 방식은 그대로 유지하되, `process_pdf_file` 함수 자체가 `async`로 변경되었음을 인지합니다. (BackgroundTasks는 async 함수도 잘 처리합니다.)

#### Phase 2: 기타 CPU 집약적 작업 전환

핵심 파이프라인 외에, 사용자의 요청에 따라 실행되는 다른 무거운 작업들도 전환합니다.

1.  **의미론적 분할 (`app/chunking.py`):**
    - `POST /api/v1/admin/apply-chunking/{doc_id}` 엔드포인트가 호출하는 핵심 청킹 함수(예: `perform_semantic_chunking`)를 찾습니다.
    - 해당 함수 내부의 CPU 집약적인 로직을 `await run_sync_in_executor`로 감싸줍니다.

2.  **시각화 이미지 생성 (`app/visualize.py`, `app/visualize_3d.py`):**
    - `GET /api/v1/document/{doc_id}/embedding_heatmap_mini` 와 같은 시각화 API 엔드포인트들을 찾습니다.
    - 이 엔드포인트들이 직접 호출하는 Matplotlib 이미지 생성 함수(예: `create_heatmap_image`)를 `await run_sync_in_executor`로 실행하도록 변경합니다.
      ```python
      # app/main.py 의 API 엔드포인트 내에서
      # 변경 전
      # image_bytes = create_heatmap_image(embedding)

      # 변경 후
      from .utils import run_sync_in_executor
      from .visualize import create_heatmap_image

      image_bytes = await run_sync_in_executor(create_heatmap_image, embedding)
      ```

### 3. 검증 계획

1.  **기능 검증:**
    - PDF를 업로드하고, OCR, 메타데이터, 임베딩이 모두 정상적으로 생성되는지 확인합니다.
    - 문서 상세 페이지에서 시각화 이미지가 올바르게 표시되는지 확인합니다.

2.  **반응성 검증 (핵심):**
    - **시나리오:** 용량이 큰 PDF 파일(수십 MB 이상)을 업로드하여 처리 파이프라인을 실행시킵니다.
    - **테스트:** PDF가 처리되는 **동시에**, 다른 터미널에서 `curl http://localhost:8000/api/v1/jobs` 와 같이 가벼운 API를 여러 번 호출합니다.
    - **기대 결과:** 서버는 PDF 처리 상태와 관계없이 `jobs` API 요청에 즉시(1초 이내) 응답해야 합니다. 만약 응답이 빠르다면, 이벤트 루프 블로킹 문제가 성공적으로 해결된 것입니다.

### 4. 장기 고려사항

- **`ThreadPoolExecutor`의 한계:** 이 방법은 현재 문제를 해결하는 훌륭한 방법이지만, 작업 실패 시 자동 재시도, 분산 처리, 정교한 모니터링 같은 고급 기능은 없습니다.
- **다음 단계:** 만약 백그라운드 작업의 복잡성이 계속 증가한다면, 다음 단계로 이 `run_sync_in_executor`로 감싼 작업들을 **Celery**와 같은 전문적인 작업 큐 시스템으로 이전하는 것을 고려할 수 있습니다. 이 계획은 Celery로의 마이그레이션을 위한 훌륭한 중간 단계가 될 것입니다.
