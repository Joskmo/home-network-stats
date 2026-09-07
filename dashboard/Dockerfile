# Explicit COPY prevents bot credentials, history, and QA artifacts entering the image.
FROM node:22-bookworm-slim@sha256:83f487e0a63425e5b4d146fb5e5be574bcbe1b7b843d3ebafdd95eaf7767a7e5 AS frontend
WORKDIR /src
COPY package.json package-lock.json tsconfig.json ./
COPY frontend ./frontend
COPY scripts ./scripts
RUN npm ci && npm run build

FROM python:3.13-slim@sha256:9d2e5553305c7c7b0097999bb17187c69b921ccd6bc9d40e4bb5ebe652c00285
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY dashboard/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --require-hashes -r requirements.txt
COPY dashboard /app/dashboard
COPY --from=frontend /src/dashboard/static/ /app/dashboard/static/
USER 1000:1000
EXPOSE 18080
CMD ["python", "-m", "dashboard"]
