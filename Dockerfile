FROM alpine:3.20

RUN apk add --no-cache build-base cmake

WORKDIR /workspace

CMD ["sh"]
