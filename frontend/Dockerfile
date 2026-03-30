# ── Stage 1: Build ───────────────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json ./
RUN npm install

COPY . .
RUN npm run build

# ── Stage 2: Serve ───────────────────────────────────────────────────────────
FROM nginx:alpine

RUN apk add --no-cache openssl

RUN rm /etc/nginx/conf.d/default.conf

# React SPA built assets
COPY --from=builder /app/dist /usr/share/nginx/html

# Generate self-signed SSL cert at build time
RUN mkdir -p /etc/nginx/ssl && \
    openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
    -keyout /etc/nginx/ssl/fintelligence.key \
    -out /etc/nginx/ssl/fintelligence.crt \
    -subj "/C=IN/ST=Maharashtra/L=Mumbai/O=Fintelligence/CN=localhost" && \
    chmod 600 /etc/nginx/ssl/fintelligence.key

# Nginx config + landing page injected at runtime via docker-compose volumes

EXPOSE 80 443

CMD ["nginx", "-g", "daemon off;"]