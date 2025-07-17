# DB 잠금 문제 심층 분석: 백그라운드 파이프라인의 비효율적 DB 쓰기 패턴

## 1. 개요

`database is locked` 오류의 근본 원인을 추가로 분석한 결과, 백그라운드 처리 파이프라인, 특히 임베딩 저장 과정에서 불필요하게 데이터베이스를 장시간 점유하는 비효율적인 코드를 발견했습니다. 이 문서는 해당 문제의 원인과 해결 방안을 기술합니다.

## 2. 문제 지점: `app/embedding.py`

- **함수**: `embed_and_store_semantic_chunks`
- **상황**: 문서에서 추출된 수십 ~ 수백 개의 시맨틱 청크(Semantic Chunk)에 대한 메타데이터를 SQLite DB에 저장하는 과정

### 2.1. 현재의 비효율적인 로직

현재 로직은 아래와 같이 `for` 루프 내에서 각 `SemanticChunk` 객체를 개별적으로 저장합니다.

```python
# 현재 로직 (app/embedding.py)

logger.info(f"Storing chunk metadata in SQLite...")
for i, (chunk, chunk_id) in enumerate(zip(chunks, chunk_ids)):
    try:
        # ... SemanticChunk 객체 생성 ...
        semantic_chunk.save() # <--- 문제 지점: 루프마다 개별 DB 트랜잭션 발생
        successful_chunk_ids.append(chunk_id)
    except Exception as e:
        # ...
        continue
```

### 2.2. 문제점

이 방식은 청크의 수만큼 (예: 100개) 개별적인 DB 쓰기 트랜잭션을 발생시킵니다. 각 트랜잭션은 짧은 시간 동안만 DB를 잠그지만, 이 작업이 수백 번 반복되면 전체 `for` 루프가 실행되는 총 시간 동안 DB는 계속해서 잠금과 해제를 반복하게 됩니다.

이로 인해 다른 프로세스(예: Zotero 가져오기 API 요청)가 DB에 쓰기 작업을 시도할 때, 이 루프 중간에 끼어들어 DB 잠금을 만날 확률이 급격히 높아집니다. 이는 `database is locked` 오류의 직접적인 원인 중 하나입니다.

## 3. 해결 방안: 일괄 삽입 (Bulk Insert)

이 문제를 해결하기 위해, Peewee ORM이 제공하는 `bulk_create` 메소드를 사용하여 모든 청크 메타데이터를 단 한 번의 DB 트랜잭션으로 삽입해야 합니다.

### 3.1. 수정 제안 코드

```python
# 개선된 로직 제안

logger.info(f"Storing chunk metadata in SQLite...")

# 1. 먼저 저장할 모든 객체를 리스트에 준비
chunks_to_save = []
for chunk, chunk_id in zip(chunks, chunk_ids):
    semantic_chunk = SemanticChunk(
        # ... 필드 설정 ...
    )
    chunks_to_save.append(semantic_chunk)

# 2. 준비된 모든 객체를 단 한 번의 쿼리로 일괄 삽입
if chunks_to_save:
    try:
        SemanticChunk.bulk_create(chunks_to_save, batch_size=100)
        successful_chunk_ids = chunk_ids
        logger.info(f"Successfully stored {len(successful_chunk_ids)} semantic chunks via bulk insert.")
    except Exception as e:
        logger.error(f"Failed to bulk save chunk metadata: {str(e)}")
        raise
```

## 4. 기대 효과 및 결론

- **기대 효과**: 수백 번에 달하던 DB 쓰기 작업이 단 한 번의 효율적인 작업으로 줄어들어, DB가 잠겨있는 총 시간이 획기적으로 감소합니다. 이는 DB 경합을 최소화하여 `database is locked` 문제 해결에 직접적으로 기여할 것입니다.

- **결론**: 이 비효율적인 쓰기 패턴은 기존에 분석된 'SQLite 동시성 제한' 문제와 맞물려 오류를 증폭시키는 핵심 요인입니다. 백엔드 개선 작업 시, **WAL 모드 활성화**와 더불어 이 **일괄 삽입 로직 적용**을 최우선으로 처리해야 합니다.
