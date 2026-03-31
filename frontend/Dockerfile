FROM node:20-alpine AS deps

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

FROM node:20-alpine AS builder

WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

ARG NEXT_PUBLIC_API_URL=https://api.oku.com.kz
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
ARG NEXT_PUBLIC_API_PREFIX=/api/v1
ENV NEXT_PUBLIC_API_PREFIX=${NEXT_PUBLIC_API_PREFIX}
ARG NEXT_PUBLIC_PUBLIC_SITE_URL=https://oku.com.kz
ENV NEXT_PUBLIC_PUBLIC_SITE_URL=${NEXT_PUBLIC_PUBLIC_SITE_URL}
ARG NEXT_PUBLIC_SITE_URL=https://oku.com.kz
ENV NEXT_PUBLIC_SITE_URL=${NEXT_PUBLIC_SITE_URL}
ARG NEXT_PUBLIC_APP_URL=https://app.oku.com.kz
ENV NEXT_PUBLIC_APP_URL=${NEXT_PUBLIC_APP_URL}
ARG NEXT_PUBLIC_APP_HOSTNAME=app.oku.com.kz
ENV NEXT_PUBLIC_APP_HOSTNAME=${NEXT_PUBLIC_APP_HOSTNAME}
ARG NEXT_PUBLIC_PUBLIC_HOSTNAME=oku.com.kz
ENV NEXT_PUBLIC_PUBLIC_HOSTNAME=${NEXT_PUBLIC_PUBLIC_HOSTNAME}

RUN npm run build

FROM node:20-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production
ENV PORT=3000

COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/package-lock.json ./package-lock.json
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/next.config.mjs ./next.config.mjs

EXPOSE 3000

CMD ["npm", "run", "start"]
