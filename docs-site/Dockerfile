# Two stages: the site is built with node, and served with nothing but the Python standard library.
FROM node:22-slim AS build
WORKDIR /site
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY server.py ./
COPY --from=build /site/.vitepress/dist ./.vitepress/dist
# PORT is supplied by the platform. See server.py.
CMD ["python", "server.py"]
