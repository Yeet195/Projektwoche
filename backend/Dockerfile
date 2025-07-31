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

RUN if [ -d .git ]; then \
    CURRENT_VERSION=$(git describe --tags --always 2>/dev/null || git rev-parse HEAD 2>/dev/null || echo "unknown") && \
    echo "Setting version to: $CURRENT_VERSION" && \
    sed -i "s/^version = .*/version = $CURRENT_VERSION/" config.ini; \
    else \
    echo "No git repository found, keeping existing version in config.ini"; \
    fi

RUN mkdir -p /app/data

CMD ["python", "app.py"]