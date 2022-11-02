# db ./ci -t ppcelery/ci:20221102-2
FROM python:3.11.0-buster

ENV TZ=UTC
ENV LC_ALL=en_US.UTF-8

RUN apt update \
    && apt-get install -y --no-install-recommends g++ make gcc git build-essential ca-certificates \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# install go
RUN wget https://go.dev/dl/go1.19.3.linux-amd64.tar.gz \
    && tar -xzf go1.19.3.linux-amd64.tar.gz \
    && mv go /opt/go \
    && ln -snf /opt/go/bin/* /usr/bin/. \
    && rm -rf go1.19.3.linux-amd64.tar.gz \
    && go version

# install go tools
RUN go install golang.org/x/vuln/cmd/govulncheck@latest \
	&& go install golang.org/x/tools/cmd/goimports@latest \
	&& go install github.com/golangci/golangci-lint/cmd/golangci-lint@latest \
    && go clean -modcache
