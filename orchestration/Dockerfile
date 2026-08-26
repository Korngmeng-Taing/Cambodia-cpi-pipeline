FROM apache/airflow:2.9.3

USER root

# Install system dependencies for Playwright Chromium, Git, and Python compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    procps \
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

# Install Python packages for Scraping, Data Processing, dbt, Testing, and Quality
RUN pip install --no-cache-dir \
    -i https://pypi.org/simple \
    --prefer-binary \
    --default-timeout=300 \
    --retries=5 \
    psycopg2-binary>=2.9.9 \
    sqlalchemy>=1.4.0 \
    pandas>=2.2.0 \
    numpy>=1.26.0 \
    scipy>=1.12.0 \
    statsmodels>=0.14.0 \
    rapidfuzz>=3.6.0 \
    curl_cffi>=0.6.0 \
    beautifulsoup4>=4.12.0 \
    playwright>=1.42.0 \
    requests>=2.31.0 \
    pytest>=8.0.0 \
    pytest-asyncio>=0.23.0 \
    httpx>=0.27.0 \
    google-generativeai>=0.4.0 \
    boto3>=1.34.0 \
    pyarrow>=15.0.0 \
    dbt-core>=1.8.0 \
    dbt-postgres>=1.8.0 \
    black>=24.0.0 \
    ruff>=0.4.0 \
    "shandy-sqlfmt[jinjafmt]>=0.21.0" \
    pre-commit>=3.7.0

# Install Playwright browser dependencies as root
USER root
RUN playwright install-deps chromium && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install Playwright Chromium browser binaries as airflow user
USER airflow
ENV PLAYWRIGHT_BROWSERS_PATH=/home/airflow/.cache/ms-playwright
RUN playwright install chromium
