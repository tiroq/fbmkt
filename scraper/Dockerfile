FROM mcr.microsoft.com/playwright/python:latest

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Install Chromium browsers (playwright image already has them, but ensure)
RUN playwright install chromium

COPY fb_marketplace_scraper.py /app/fb_marketplace_scraper.py
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Data volume
VOLUME ["/data"]

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["/app/entrypoint.sh"]
