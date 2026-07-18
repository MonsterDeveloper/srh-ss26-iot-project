FROM oven/bun:1-alpine AS development-dependencies
WORKDIR /app
COPY package.json bun.lock ./
RUN bun install --frozen-lockfile

FROM oven/bun:1-alpine AS production-dependencies
WORKDIR /app
COPY package.json bun.lock ./
RUN bun install --frozen-lockfile --production

FROM oven/bun:1-alpine AS build
WORKDIR /app
COPY --from=development-dependencies /app/node_modules ./node_modules
COPY . .
RUN bun run build

FROM node:24-alpine AS production
ENV NODE_ENV=production \
    PORT=3000 \
    TZ=Europe/Berlin
WORKDIR /app
COPY --chown=node:node package.json ./
COPY --chown=node:node --from=production-dependencies /app/node_modules ./node_modules
COPY --chown=node:node --from=build /app/build ./build
USER node
EXPOSE 3000
CMD ["./node_modules/.bin/react-router-serve", "./build/server/index.js"]
