FROM golang:1.22-alpine
RUN addgroup -g 10001 sandbox && adduser -u 10001 -G sandbox -s /bin/sh -D sandbox
USER sandbox
WORKDIR /workspace
