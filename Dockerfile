FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

RUN useradd -m appuser
WORKDIR /app

COPY pyproject.toml .
RUN uv sync --no-dev

COPY . .

RUN chown -R appuser:appuser /app
USER appuser

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app"
CMD ["moon"]
