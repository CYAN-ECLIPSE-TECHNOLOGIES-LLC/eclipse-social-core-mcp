FROM python:3.12-slim
LABEL io.modelcontextprotocol.server.name="io.github.CYAN-ECLIPSE-TECHNOLOGIES-LLC/social-core"
WORKDIR /app
COPY server.py bazaar-manifest.json ./
COPY fixtures ./fixtures
RUN useradd -r appuser && mkdir -p /app/data && chown appuser /app/data
USER appuser
ENTRYPOINT ["python", "server.py"]
