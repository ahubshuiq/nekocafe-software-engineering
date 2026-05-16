# ============ 阶段一：构建 ============
FROM node:20-alpine AS builder

WORKDIR /build

COPY package.json package-lock.json ./
RUN npm ci --only=production --ignore-scripts
# ============ 阶段二：运行 ============
FROM node:20-alpine AS runtime

RUN addgroup -S nekocafe && adduser -S nekocafe -G nekocafe

WORKDIR /app

COPY --from=builder /build/node_modules ./node_modules
COPY src/ ./src/
COPY package.json ./

ENV TZ=Asia/Shanghai
RUN apk add --no-cache tzdata && cp /usr/share/zoneinfo/$TZ /etc/localtime

USER nekocafe

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD wget -qO- http://localhost:3000/health || exit 1

CMD ["node", "src/index.js"]
