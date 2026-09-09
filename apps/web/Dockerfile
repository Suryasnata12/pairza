FROM node:22-alpine AS builder
WORKDIR /app

COPY package.json ./
RUN npm install

COPY . .

# Both of these get baked into the image at build time. The WS URL is
# straightforward — it's read directly in browser code, and Next.js always
# inlines NEXT_PUBLIC_* vars into the client bundle at build time. The API
# URL is less obvious: it's only ever read inside next.config.mjs's
# rewrites() function, but Next.js evaluates that function ONCE at build
# time to produce a fixed routing manifest, not per-request at runtime —
# so this has to be a build arg too, not a runtime environment variable,
# or docker-compose.yml setting it later would silently have no effect.
# Defaults here match running outside Docker entirely (`npm run dev`);
# docker-compose.yml passes the real values for the actual container setup.
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
