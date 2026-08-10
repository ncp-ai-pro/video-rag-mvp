FROM node:22-slim AS web-builder

WORKDIR /web

COPY web/package*.json ./
RUN npm ci

COPY web ./

# The local all-in-one Docker image serves React from the API origin, so the
# browser must call API endpoints without the production /api reverse-proxy prefix.
ARG VITE_API_BASE=""
ARG VITE_CHAT_BASE=""
ENV VITE_API_BASE=${VITE_API_BASE} \
    VITE_CHAT_BASE=${VITE_CHAT_BASE}
RUN npm run build


FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# ffmpeg is used by yt-dlp when a subtitle format needs conversion.
RUN apt-get update \
    && apt-get install --no-install-recommends -y ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt

RUN addgroup --system --gid 10001 app \
    && adduser --system --uid 10001 --ingroup app --home /app app

COPY app ./app
COPY --from=web-builder /web/dist ./app/static
RUN mkdir -p /app/data \
    && chown -R app:app /app

USER app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
