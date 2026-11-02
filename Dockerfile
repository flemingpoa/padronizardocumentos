# Imagem para publicar o Prumo em um servidor (Render, Railway, Fly.io, VPS etc.)
FROM python:3.12-slim

# LibreOffice (conversões e PDF), Tesseract com português (OCR) e fontes compatíveis com as do Word
RUN apt-get update && apt-get install -y --no-install-recommends \
        libreoffice-writer tesseract-ocr tesseract-ocr-por \
        fonts-liberation fonts-crosextra-carlito fonts-crosextra-caladea fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app app
COPY web web

ENV PRUMO_DADOS=/dados
RUN useradd -m prumo && mkdir -p /dados && chown prumo /dados
USER prumo
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers"]
