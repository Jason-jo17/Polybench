FROM golang:1.22-alpine
RUN addgroup -g 10001 sandbox && adduser -u 10001 -G sandbox -s /bin/sh -D sandbox

# Pre-compile the standard library packages tasks commonly use, so `go test` in
# the sandbox doesn't rebuild them on every run. At run time the sandbox copies
# this read-only cache into its writable /tmp (see sandbox/languages.py).
ENV GOCACHE=/opt/gocache GOFLAGS=-vet=off GOTOOLCHAIN=local
RUN mkdir -p /opt/gocache /tmp/warm && cd /tmp/warm \
 && printf 'module warm\n\ngo 1.22\n' > go.mod \
 && printf 'package warm\n\nimport (\n\t"errors"\n\t"fmt"\n\t"math"\n\t"sort"\n\t"strconv"\n\t"strings"\n\t"sync"\n\t"time"\n\t"unicode"\n)\n\nvar _ = []any{errors.New, fmt.Sprint, math.Abs, sort.Ints, strconv.Itoa, strings.Fields, sync.NewCond, time.Now, unicode.IsLetter}\n' > warm.go \
 && printf 'package warm\n\nimport "testing"\n\nfunc TestWarm(t *testing.T) {}\n' > warm_test.go \
 && go test ./... \
 && cd / && rm -rf /tmp/warm \
 && chmod -R a+rX /opt/gocache

USER sandbox
WORKDIR /workspace
