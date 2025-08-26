FROM golang:1.22-alpine AS build
WORKDIR /app

# cache deps
COPY go.mod go.sum ./
RUN go mod download

# source
COPY . .
RUN go build -o /bin/api ./cmd/server

FROM golang:1.22-alpine
WORKDIR /app
COPY --from=build /bin/api /srv/api
COPY --from=build /app/go.mod /app/go.sum /app/
COPY --from=build /app/internal /app/internal/
COPY --from=build /app/cmd /app/cmd/
EXPOSE 8082
CMD ["/srv/api"]
