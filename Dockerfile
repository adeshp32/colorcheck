FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV VCC_STORAGE_DIR=/app/storage

WORKDIR /app

RUN apt-get update \
  && apt-get install -y --no-install-recommends ffmpeg \
  && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./

RUN python -m pip install --upgrade pip \
  && python -m pip install --no-cache-dir \
    "fastapi>=0.115.0" \
    "jinja2>=3.1.4" \
    "numpy>=1.26.4" \
    "opencv-python-headless>=4.10.0.84" \
    "pillow>=10.4.0" \
    "python-multipart>=0.0.9" \
    "uvicorn[standard]>=0.30.6" \
    "filelock" \
    "fsspec>=0.8.5" \
    "networkx>=2.5.1" \
    "setuptools>=77.0.3" \
    "sympy>=1.13.3" \
    "typing-extensions>=4.8.0" \
  && python -m pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu "torch>=2.3.0"

COPY src ./src

RUN python -m pip install --no-cache-dir --no-deps .

RUN useradd --create-home --uid 10001 appuser \
  && mkdir -p /app/storage \
  && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:' + __import__('os').environ.get('PORT', '8000') + '/healthz', timeout=3)"

CMD ["sh", "-c", "exec uvicorn colorcheck.web.app:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --proxy-headers --forwarded-allow-ips='*'"]
