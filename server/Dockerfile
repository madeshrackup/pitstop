# Build WiiLink wfc-server (wwfc) for Pitstop
FROM golang:1.24-bookworm AS build
WORKDIR /src
RUN git clone --depth 1 https://github.com/WiiLink24/wfc-server.git .
# Stage1 v1 clients hash the full /payload query; stock code only hashed g+s → 20913
COPY patch-salt-hash.py /tmp/patch-salt-hash.py
RUN python3 /tmp/patch-salt-hash.py
ENV GOTOOLCHAIN=auto
RUN go build -o /out/wwfc .

FROM debian:bookworm-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=build /out/wwfc /app/wwfc
COPY game_list.tsv /app/game_list.tsv
RUN mkdir -p /app/payload /app/logs /app/state
EXPOSE 80 443 28910 29900 29901 29920 29997 27900/udp 27901/udp
CMD ["/app/wwfc"]
