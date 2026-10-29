# Production image for the Vite/React frontend.
#
# Railway builds this file when the service root is `frontend/`. VITE_* values
# are compile-time build arguments; API_ORIGIN/CLERK_FAPI_ORIGIN/HSTS_* are
# runtime container variables used by Nginx.
FROM node:24.15.0-bookworm-slim AS build

ARG VITE_API_URL
ARG VITE_CLERK_PUBLISHABLE_KEY

ENV VITE_API_URL=$VITE_API_URL \
    VITE_CLERK_PUBLISHABLE_KEY=$VITE_CLERK_PUBLISHABLE_KEY

WORKDIR /app

RUN npm install --global npm@12.2.0

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:1.29-alpine AS runtime

RUN apk add --no-cache gettext

COPY nginx.conf.template /etc/nginx/nginx.conf.template
COPY --chmod=0755 docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
COPY --from=build /app/dist /usr/share/nginx/html

ENV HSTS_ENABLED=false \
    HSTS_MAX_AGE_SECONDS=31536000

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1:8080/healthz || exit 1

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
