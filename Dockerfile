# 1단계: 베이스 이미지 선택 (경량화된 Python 3.11 Slim 버전 사용)
FROM python:3.11-slim

# 2단계: 작업 디렉토리 설정
WORKDIR /app

# 3단계: 필수 의존성 패키지 복사 및 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4단계: 애플리케이션 소스 코드 복사
COPY main.py .

# 5단계: FastAPI 서비스 포트 노출 (기본값: 8000)
EXPOSE 8000

# 6단계: 컨테이너 실행 명령어 정의
# uvicorn을 사용해 FastAPI 앱을 호스트 0.0.0.0, 포트 8000으로 실행합니다.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
