# 过盈配合核算服务镜像 —— 运行时按 Python 3.12
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

# 先装依赖，利用层缓存
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 再拷代码
COPY app ./app

EXPOSE 8000

# slim 镜像没有 curl，健康检查直接用标准库
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import json,urllib.request;r=urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=3);assert json.load(r)['status']=='ok'" || exit 1

# 容器一起来，接触计算接口即对外可用
CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000"]
