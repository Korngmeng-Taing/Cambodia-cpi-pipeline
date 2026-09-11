FROM apache/airflow:2.9.3-python3.11

USER root

# Install system dependencies for Playwright Chromium, Git, Python compilation, and psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    procps \
    libpq-dev \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libatspi2.0-0 \
    libasound2 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

USER airflow
ENV PATH="/home/airflow/.local/bin:${PATH}"

COPY requirements.txt /opt/airflow/requirements.txt

# Install Python packages via requirements.txt for stable dependency resolution
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /opt/airflow/requirements.txt

# Install Playwright browser dependencies as root
USER root
RUN playwright install-deps chromium && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install Playwright Chromium browser binaries as airflow user
USER airflow
ENV PLAYWRIGHT_BROWSERS_PATH=/home/airflow/.cache/ms-playwright
ENV PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright/
RUN playwright install --no-shell chromium
