# ============ 阶段一：构建 ============
FROM python:3.12-slim AS builder

WORKDIR /build

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ============ 阶段二：运行 ============
FROM python:3.12-slim AS runtime

RUN groupadd -r nekocafe && useradd -r -g nekocafe nekocafe

WORKDIR /app

COPY --from=builder /install /usr/local
COPY src/ ./src/

ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime

USER nekocafe

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
