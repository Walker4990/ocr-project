# 빌드 컨텍스트는 저장소 루트다 (npm workspaces의 package-lock.json이 루트에 있다)
FROM node:22-slim AS build
WORKDIR /repo

COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/
RUN npm ci

COPY apps/web apps/web
# NEXT_PUBLIC_* 값은 빌드 때 번들에 박힌다. 브라우저가 호출하는 주소여야 한다
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_TELEMETRY_DISABLED=1
RUN npm run build --workspace web && npm prune --omit=dev

FROM node:22-slim
WORKDIR /repo
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1

COPY --from=build --chown=node:node /repo /repo
USER node
EXPOSE 3000
CMD ["npm", "run", "start", "--workspace", "web"]
