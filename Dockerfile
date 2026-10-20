FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv/app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && pip install --no-cache-dir "psycopg[binary]"

COPY app ./app
COPY scripts ./scripts
COPY wsgi.py run.py ./

RUN useradd --system --uid 1001 gestion && mkdir -p /srv/data && chown -R gestion /srv/data /srv/app
USER gestion

ENV DATA_DIR=/srv/data
VOLUME ["/srv/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=4s --start-period=10s \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/sante')"

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60", "wsgi:application"]
