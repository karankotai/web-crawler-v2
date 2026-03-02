FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gcc libxml2-dev libxslt-dev && rm -rf /var/lib/apt/lists/*
COPY rag_app/requirements.txt ./rag_app/requirements.txt
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r rag_app/requirements.txt -r requirements.txt pymongo
COPY rag_app/ ./rag_app/
COPY crawlers/ ./crawlers/
COPY config.py main.py ./
RUN mkdir -p ./output
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "rag_app.main:app", "--host", "0.0.0.0", "--port", "8000"]
