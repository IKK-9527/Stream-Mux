FROM python:3.11-slim
LABEL authors="ikk"
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir -r requirements.txt
CMD ["python", "app.py"]
EXPOSE 5000
ENV TZ=Asia/Shanghai
