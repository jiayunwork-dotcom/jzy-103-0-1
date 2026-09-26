# 语法版本按运行时 Python 3.12；镜像内一键跑测试与启动服务。
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 先装依赖，利用层缓存。
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt

# 拷贝应用与测试。
COPY app ./app
COPY tests ./tests
COPY pytest.ini ./pytest.ini

EXPOSE 8000

# 容器一起来，接触计算接口即对外可用。
# 交付测试可：docker run --rm <image> python -m pytest
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
