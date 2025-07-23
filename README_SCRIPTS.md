# 🛠️ RefServerLite Development Scripts

Docker 없이 빠른 개발을 위한 스크립트들입니다.

## 📋 스크립트 목록

### 🔧 `scripts/setup_dev.sh` - 개발 환경 설정
```bash
scripts/setup_dev.sh
```
- 시스템 의존성 확인 및 설치 (tesseract, build-tools)
- Python 의존성 설치 (`pip install -r requirements.txt`)
- 가상환경 사용 권장 및 확인

### 🚀 `scripts/run_server.sh` - 서버 실행
```bash
scripts/run_server.sh
```
- 데이터 및 로그 디렉토리 생성 (`refdata/`, `logs/`)
- 데이터베이스 마이그레이션 실행
- 관리자 계정 초기화 (admin/admin123)
- 포트 8000 충돌 확인 및 기존 서버 중지
- `--reload` 모드로 개발 서버 실행
- 서버 로그를 `logs/server.log`에 저장

### 🛑 `scripts/stop_server.sh` - 서버 중지
```bash
scripts/stop_server.sh
```
- 실행 중인 uvicorn 프로세스 찾기
- Graceful shutdown 시도 (SIGTERM)
- 필요시 강제 종료 (SIGKILL)
- 서버 로그 위치 안내

### 🔍 `scripts/check_server.sh` - 서버 상태 확인
```bash
scripts/check_server.sh
```
- 프로세스 실행 여부 확인
- 포트 8000 리스닝 상태 확인
- HTTP 응답 테스트 (200 OK)
- 데이터베이스 & ChromaDB 상태 확인
- 최신 서버 로그 표시 (마지막 5줄)

## 🗂️ 디렉토리 구조

```
RefServerLite/
├── scripts/              # 개발 스크립트들
│   ├── setup_dev.sh      # 환경 설정
│   ├── run_server.sh     # 서버 실행
│   ├── stop_server.sh    # 서버 중지
│   └── check_server.sh   # 상태 확인
├── logs/                 # 서버 로그
│   └── server.log        # 실시간 서버 로그
└── refdata/              # 데이터 저장소
    ├── refserver.db      # SQLite 데이터베이스
    ├── pdfs/             # 업로드된 PDF 파일
    └── chromadb/         # 벡터 임베딩 저장소
```

## 🚀 빠른 시작

```bash
# 1. 최초 환경 설정 (한 번만)
scripts/setup_dev.sh

# 2. 서버 실행
scripts/run_server.sh

# 3. 다른 터미널에서 상태 확인
scripts/check_server.sh

# 4. 서버 중지
scripts/stop_server.sh
```

## 🌐 접속 정보

- **서버 URL**: http://localhost:8000
- **관리자 로그인**: admin / admin123
- **서버 로그**: `logs/server.log`

## 💡 팁

- 모든 스크립트는 **RefServerLite 루트 디렉토리**에서 실행해야 합니다
- 가상환경 사용을 권장합니다
- `--reload` 모드로 실행되므로 코드 변경 시 자동 재시작됩니다
- 로그는 실시간으로 `logs/server.log`에 저장됩니다