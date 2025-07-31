FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    iputils-ping \
    net-tools \
    iproute2 \
    git \
    && rm -rf /var/lib/apt/lists/*

ENV DOCKER_CONTAINER=true

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data

CMD ["python", "app.py"]