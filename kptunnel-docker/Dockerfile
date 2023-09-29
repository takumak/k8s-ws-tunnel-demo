FROM golang:1.19-bullseye as builder
WORKDIR /kptunnel
RUN git clone https://github.com/ifritJP/kptunnel.git .
RUN git checkout 2d0862f1bf3506e56fe4483fdd0952f4117c44f0
RUN CGO_ENABLED=0 make build

FROM busybox:1.36-musl
COPY --from=builder /kptunnel/kptunnel /
