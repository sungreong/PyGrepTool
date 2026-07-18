FROM python:3.12-slim AS wheel-builder

WORKDIR /build

COPY pyproject.toml README.md ./
COPY src ./src

# Build the artifact that users install. The runtime image never receives src/.
RUN python -m pip wheel --no-deps --wheel-dir /wheel .


FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    LC_ALL=C.UTF-8 \
    LANG=C.UTF-8

RUN apt-get update \
    && apt-get install -y --no-install-recommends ripgrep grep \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=wheel-builder /wheel /wheel
COPY pyproject.toml ./
COPY tests ./tests
COPY examples ./examples
COPY scripts ./scripts
COPY skills ./skills
COPY standalone ./standalone

# Install only the built wheel plus test-only dependencies. Do not add /app/src
# or the source checkout to PYTHONPATH: imports must resolve from site-packages.
RUN python -m pip install --upgrade pip \
    && python -m pip install /wheel/pygreptool-*.whl "pytest>=8.2,<9" \
    && python -c "import pygreptool; print(pygreptool.__file__)" \
    && rm -rf /wheel

CMD ["pytest", "-q"]


# Opt-in image for the live LangChain example. The default runtime image above
# stays dependency-minimal and does not contain a model provider SDK.
FROM runtime AS agent-demo

RUN python -m pip install \
    "langchain>=1.0,<2.0" \
    "langchain-core>=1.0,<2.0" \
    "langchain-openai>=1.0,<2.0"


# Keep the default `docker build .` and ordinary Compose services minimal.
FROM runtime AS final
