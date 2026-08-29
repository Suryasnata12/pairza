FROM node:22-alpine AS builder
WORKDIR /app

COPY package.json ./
RUN npm install

COPY . .

# Baked into the client bundle at build time — see next.config.mjs and
# lib/use-session-socket.ts for why these two are treated differently:
# NEXT_PUBLIC_API_URL is only read server-side (in the rewrites() function,
# at request time) so it could be a runtime env var instead, but the
# WS URL is read directly in browser code and Next.js inlines
# NEXT_PUBLIC_* vars into the client bundle at build time, so it has to be
# available here. Defaults match the standard docker-compose setup, where
# the browser reaches every service through the host's published ports.
# Baked into the client bundle at build time — see next.config.mjs and
# lib/use-session-socket.ts for why these two are treated differently:
# NEXT_PUBLIC_API_URL is only read server-side (in the rewrites() function,
# at request time) so it's supplied as a normal runtime env var by
# docker-compose instead. The WS URL IS read directly in browser code, and
# Next.js inlines NEXT_PUBLIC_* vars into the client bundle at build time,
# so it has to be available here, with a default matching local dev outside
# Docker (`npm run dev`).
ARG NEXT_PUBLIC_WS_URL=ws://localhost:8000
ENV NEXT_PUBLIC_WS_URL=$NEXT_PUBLIC_WS_URL
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production

COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3000
CMD ["node", "server.js"]
