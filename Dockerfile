FROM python:3.11-alpine
LABEL authors="ikk"
WORKDIR /app

# 安装依赖（利用docker缓存层）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码（仅复制需要文件，不要整个目录）
COPY app.py main.py config.py ./
COPY templates ./templates
COPY static ./static

EXPOSE 8899
ENV TZ=Asia/Shanghai
CMD ["python", "app.py"]
