# Сайт дашборда (E9): Next.js standalone.
FROM node:24-slim AS build
WORKDIR /web
RUN corepack enable
COPY web/package.json web/pnpm-lock.yaml web/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY web/ ./
RUN mkdir -p public && pnpm build  # public/ пустая и в git не хранится

FROM node:24-slim
WORKDIR /web
ENV NODE_ENV=production HOSTNAME=0.0.0.0 PORT=3000
COPY --from=build /web/.next/standalone ./
COPY --from=build /web/.next/static ./.next/static
COPY --from=build /web/public ./public
USER node
CMD ["node", "server.js"]
