FROM alpine:3.20

RUN apk add --no-cache build-base cmake

WORKDIR /workspace

COPY entry.sh /usr/local/bin/entry.sh
RUN chmod +x /usr/local/bin/entry.sh

ENTRYPOINT ["/usr/local/bin/entry.sh"]
CMD ["shell"]
