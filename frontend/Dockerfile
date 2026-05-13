# Dev-mode image for the Next.js frontend.
FROM node:20-alpine AS base

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 3000

FROM base AS dev
CMD ["npm", "run", "dev", "--", "--hostname", "0.0.0.0"]

FROM base AS prod
RUN npm run build
CMD ["npm", "start"]
