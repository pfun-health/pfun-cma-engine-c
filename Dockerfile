# syntax=docker/dockerfile:1.7

FROM alpine:3.20

RUN apk add --no-cache \
    build-base \
    git \
    gcc \
    g++ \
    make \
    cmake \
    musl-dev \
    llvm17 \
    llvm17-dev \
    llvm17-static

WORKDIR /workspace

ARG ENABLE_UV_DEMO_SETUP=true

COPY pyproject.toml uv.lock ./

ENV LLVM_CONFIG=/usr/bin/llvm-config-17
ENV LLVM_DIR=/usr/lib/cmake/llvm17
ENV CMAKE_PREFIX_PATH=/usr/lib/cmake/llvm17:/usr/lib/cmake

RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=cache,target=/root/.cache/uv \
    if [ "$ENABLE_UV_DEMO_SETUP" = "true" ]; then \
    apk add --no-cache python3 py3-pip && \
    python3 -m pip install --break-system-packages uv && \
    cd / && \
    git clone https://github.com/numba/llvmlite.git && \
    cd ./llvmlite && \
    export LLVM_CONFIG='/usr/bin/llvm-config-17' && \
    uv run python3 setup.py build && \
    uv run python3  setup.py install && \
    cd /workspace && \
    rm -rf /llvmlite && \
    uv sync --dev --no-install-project; \
    fi

COPY setup.py README.md demo.py demo_jit.py ./
COPY pfun_cma_engine ./pfun_cma_engine
COPY src ./src

RUN --mount=type=cache,target=/root/.cache/uv \
    if [ "$ENABLE_UV_DEMO_SETUP" = "true" ]; then \
    uv sync --dev; \
    fi

COPY entry.sh /usr/local/bin/entry.sh
RUN chmod +x /usr/local/bin/entry.sh

ENTRYPOINT ["/usr/local/bin/entry.sh"]
CMD ["shell"]
