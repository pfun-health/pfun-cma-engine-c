# syntax=docker/dockerfile:1.7

FROM alpine:3.20

RUN apk add --no-cache build-base cmake llvm llvm-dev clang lld

ENV LLVM_DIR=/usr/lib/cmake/llvm
ENV CMAKE_PREFIX_PATH=/usr/lib/cmake/llvm:/usr/lib/cmake

WORKDIR /workspace

ARG ENABLE_UV_DEMO_SETUP=false

COPY pyproject.toml uv.lock ./

RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=cache,target=/root/.cache/uv \
    if [ "$ENABLE_UV_DEMO_SETUP" = "true" ]; then \
      apk add --no-cache python3 py3-pip && \
      python3 -m pip install --break-system-packages uv && \
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
