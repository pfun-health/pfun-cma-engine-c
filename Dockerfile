FROM alpine:3.20

RUN apk add --no-cache build-base cmake

WORKDIR /workspace

ARG ENABLE_UV_DEMO_SETUP=false

COPY pyproject.toml uv.lock setup.py README.md demo.py demo_jit.py ./
COPY pfun_cma_engine ./pfun_cma_engine
COPY src ./src

RUN if [ "$ENABLE_UV_DEMO_SETUP" = "true" ]; then \
      apk add --no-cache python3 py3-pip && \
      python3 -m pip install --no-cache-dir --break-system-packages uv && \
      uv sync --dev; \
    fi

COPY entry.sh /usr/local/bin/entry.sh
RUN chmod +x /usr/local/bin/entry.sh

ENTRYPOINT ["/usr/local/bin/entry.sh"]
CMD ["shell"]
