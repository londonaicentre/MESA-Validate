FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

RUN apt-get update && apt-get install -y git
WORKDIR /app
COPY . .
RUN uv sync --locked
RUN useradd app && chown -R app sessions
USER app
CMD [".venv/bin/streamlit", "run", "Home.py"]
