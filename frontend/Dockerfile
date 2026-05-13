# ── builder ────────────────────────────────────────────────────────────────────
FROM node:22-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci --prefer-offline

COPY . .

# VITE_API_BASE="" → relative URLs → nginx proxies /api/ internally.
# Override at build time for external backends: --build-arg VITE_API_BASE=https://api.example.com
ARG VITE_API_BASE=""
ENV VITE_API_BASE=${VITE_API_BASE}

RUN npm run build

# ── runtime ────────────────────────────────────────────────────────────────────
FROM nginx:1.27-alpine

# Drop default config
RUN rm -f /etc/nginx/conf.d/default.conf

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://localhost/health-check >/dev/null 2>&1 || exit 1

CMD ["nginx", "-g", "daemon off;"]
