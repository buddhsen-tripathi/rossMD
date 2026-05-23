# Ross MD — frontend (Next.js, standalone output).
# Build context is the web/ directory (see .do/app.yaml source_dir).
FROM node:22-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-slim AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# NEXT_PUBLIC_* is inlined at build time. Empty string => the browser calls the
# API same-origin at /api/* (App Platform routes /api to the backend service).
ARG NEXT_PUBLIC_API=""
ENV NEXT_PUBLIC_API=$NEXT_PUBLIC_API
RUN npm run build

FROM node:22-slim AS runner
WORKDIR /app
ENV NODE_ENV=production \
    HOSTNAME=0.0.0.0 \
    PORT=8080
# Next standalone bundle: server.js + minimal node_modules, plus static assets
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
EXPOSE 8080
CMD ["node", "server.js"]
