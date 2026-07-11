FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    LC_ALL=C.UTF-8 \
    LANG=C.UTF-8

RUN apt-get update \
    && apt-get install -y --no-install-recommends ripgrep grep \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md requirements.txt ./
COPY src ./src
COPY tests ./tests
COPY examples ./examples
COPY scripts ./scripts
COPY tools ./tools

RUN pip install --upgrade pip \
    && pip install -r requirements.txt

CMD ["pytest", "-q"]
