# Native Server Scripts Implementation - 2025.07.23

## 🎯 목적

Docker 빌드 시간을 절약하고 더 빠른 개발을 위해 Docker 없이 서버를 직접 실행할 수 있는 스크립트 시스템을 구현했습니다.

## 📋 배경

### 문제점
- Docker 이미지 빌드 시간이 오래 걸림 (특히 matplotlib, chroma-hnswlib 컴파일)
- 코드 변경 후 테스트까지 시간이 많이 소요
- 개발 속도 저하

### 해결 방안
- Native Python 환경에서 직접 서버 실행
- 필요한 시스템 의존성만 설치
- Docker와 동일한 데이터 디렉토리 공유

## 🛠️ 구현 내용

### 1. 시스템 의존성 분석

**Docker에서 설치하는 시스템 패키지들:**
```dockerfile
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-eng \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1
```

**실제 필요한 패키지:**
- `tesseract-ocr` + `tesseract-ocr-eng`: OCR 기능
- `build-essential` + `python3-dev`: matplotlib/chroma-hnswlib 컴파일용

### 2. 스크립트 아키텍처

```
scripts/
├── setup_dev.sh      # 환경 설정 (한 번만 실행)
├── run_server.sh     # 서버 실행 (메인 스크립트)
├── stop_server.sh    # 서버 중지
└── check_server.sh   # 상태 확인
```

### 3. 각 스크립트 기능

#### `setup_dev.sh` - 환경 설정
```bash
# 주요 기능
1. Python 버전 확인 (3.8+)
2. 가상환경 사용 권장
3. 시스템 의존성 자동 설치
   - tesseract-ocr 
   - build-essential
   - python3-dev
4. Python 패키지 설치 (requirements.txt)
```

#### `run_server.sh` - 서버 실행
```bash
# 주요 기능
1. 실행 환경 검증
   - 올바른 디렉토리 확인
   - Python 버전 확인
   - tesseract 설치 확인
   - Python 패키지 확인
2. 데이터베이스 준비
   - 디렉토리 생성 (refdata/, logs/)
   - 마이그레이션 실행
   - 관리자 계정 생성
3. 서버 실행
   - 기존 서버 충돌 확인 및 중지
   - uvicorn --reload 모드 실행
   - 로그를 logs/server.log에 저장
```

#### `stop_server.sh` - 서버 중지
```bash
# 주요 기능
1. 실행 중인 uvicorn 프로세스 찾기
2. Graceful shutdown (SIGTERM)
3. 10초 대기 후 강제 종료 (SIGKILL)
4. 로그 파일 위치 안내
```

#### `check_server.sh` - 상태 확인
```bash
# 주요 기능
1. 프로세스 실행 상태
2. 포트 8000 리스닝 상태
3. HTTP 응답 테스트 (curl)
4. 데이터베이스 파일 존재 확인
5. ChromaDB 디렉토리 확인
6. 최신 로그 표시 (마지막 5줄)
```

## 📁 디렉토리 구조 개선

### 기존 구조
```
RefServerLite/
├── run_server.sh     # 루트에 스크립트들이 분산
├── setup_dev.sh
├── stop_server.sh
├── check_server.sh
└── server.log        # 루트에 로그 파일
```

### 개선된 구조
```
RefServerLite/
├── scripts/          # 스크립트 전용 디렉토리
│   ├── setup_dev.sh
│   ├── run_server.sh
│   ├── stop_server.sh
│   └── check_server.sh
├── logs/             # 로그 전용 디렉토리
│   └── server.log
├── refdata/          # 데이터 저장소 (Docker와 공유)
│   ├── refserver.db
│   ├── pdfs/
│   └── chromadb/
└── README_SCRIPTS.md # 스크립트 사용법 문서
```

## 🔧 기술적 세부사항

### 1. 데이터베이스 공유
- Docker와 Native 모두 `./refdata/` 사용
- SQLite 파일: `refdata/refserver.db`
- ChromaDB: `refdata/chromadb/`
- PDF 파일: `refdata/pdfs/`

### 2. 로그 관리
- 실시간 로그 출력 + 파일 저장
- `tee` 명령어 사용: `uvicorn ... 2>&1 | tee logs/server.log`
- 기존 로그와 새 로그 위치 모두 지원

### 3. 프로세스 관리
```bash
# 프로세스 찾기
pgrep -f "uvicorn.*app.main:app"

# 포트 확인
lsof -i:8000

# Graceful shutdown
kill $PID
# Force kill after timeout
pkill -9 -f "uvicorn.*app.main:app"
```

### 4. 환경 설정
```bash
# Python 경로 설정
export PYTHONPATH=$(pwd)

# 실행 옵션
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## ✅ 검증 결과

### 성공적인 기능 확인
1. ✅ SQLite 데이터베이스 초기화
2. ✅ ChromaDB 클라이언트 생성  
3. ✅ 백그라운드 작업 프로세서 시작
4. ✅ 웹 서버 응답 (HTTP 200 OK)
5. ✅ Admin 페이지 접근 가능
6. ✅ 로그인 기능 동작
7. ✅ API 엔드포인트 정상 응답

### 성능 비교
- **Docker 방식**: 빌드 시간 2-5분 + 시작 시간 30초
- **Native 방식**: 시작 시간 5-10초
- **개발 효율성**: 약 10-20배 향상

## 🚀 사용 흐름

### 최초 설정 (한 번만)
```bash
# 1. 가상환경 활성화 (권장)
source venv/bin/activate

# 2. 환경 설정
scripts/setup_dev.sh
```

### 일상적인 개발
```bash
# 서버 시작
scripts/run_server.sh

# 브라우저에서 http://localhost:8000 접속
# admin / admin123 로 로그인

# 코드 수정 시 자동 재시작됨 (--reload)

# 서버 상태 확인 (다른 터미널)
scripts/check_server.sh

# 개발 완료 후 서버 중지
scripts/stop_server.sh
```

## 📝 주의사항

### 1. 실행 위치
- 반드시 RefServerLite 루트 디렉토리에서 실행
- `app/main.py` 파일 존재 확인으로 검증

### 2. 의존성 관리
- 가상환경 사용 강력 권장
- tesseract OCR 필수 설치
- build-essential (matplotlib 컴파일용)

### 3. 포트 충돌
- Docker와 동시 실행 불가 (같은 8000 포트)
- 스크립트에서 자동으로 기존 서버 중지

### 4. 데이터 공유
- Docker와 Native가 같은 데이터 사용
- 운영 환경은 별도 머신에서 실행 예정

## 🔮 향후 개선사항

### 1. 추가 기능
- [ ] 개발/운영 환경 분리 옵션
- [ ] 로그 레벨 설정 옵션
- [ ] 백그라운드 실행 모드
- [ ] Health check 스크립트

### 2. 문서화
- [x] README_SCRIPTS.md 생성
- [x] devlog 문서 작성
- [ ] 트러블슈팅 가이드

### 3. 자동화
- [ ] pre-commit hook 연동
- [ ] 테스트 실행 스크립트
- [ ] 배포 스크립트

## 💡 결론

Docker 없이 Native 환경에서 서버를 실행할 수 있는 완전한 스크립트 시스템을 구축했습니다. 이를 통해:

1. **개발 속도 대폭 향상** - Docker 빌드 시간 제거
2. **편리한 디버깅** - 직접적인 Python 환경 접근
3. **자동화된 환경 설정** - 복잡한 설정 과정 단순화
4. **체계적인 관리** - 스크립트와 로그의 조직적 관리

특히 Docker와 데이터를 공유하면서도 개발 편의성을 크게 개선할 수 있었습니다.