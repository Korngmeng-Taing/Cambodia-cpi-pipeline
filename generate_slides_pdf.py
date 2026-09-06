import os
import base64
import subprocess

# Paths
workspace = r"d:\CPI PIPELINE"
images = {
    "basket": r"C:\Users\Lenovo\.gemini\antigravity\brain\2c4e515f-0651-49c2-a1df-c1426d221ca5\.user_uploaded\media_1788663086377.png",
    "why_cpi": r"C:\Users\Lenovo\.gemini\antigravity\brain\2c4e515f-0651-49c2-a1df-c1426d221ca5\.user_uploaded\media_1788663095921.png",
    "groups": r"C:\Users\Lenovo\.gemini\antigravity\brain\2c4e515f-0651-49c2-a1df-c1426d221ca5\.user_uploaded\media_1788663111614.png",
    "framework": r"C:\Users\Lenovo\.gemini\antigravity\brain\2c4e515f-0651-49c2-a1df-c1426d221ca5\.user_uploaded\media_1788663147557.png",
    "architecture": r"C:\Users\Lenovo\.gemini\antigravity\brain\2c4e515f-0651-49c2-a1df-c1426d221ca5\.user_uploaded\media_1788663184991.png",
}

b64_img = {}
for k, path in images.items():
    if os.path.exists(path):
        with open(path, "rb") as f:
            b64_img[k] = f"data:image/png;base64,{base64.b64encode(f.read()).decode('utf-8')}"
    else:
        b64_img[k] = ""

html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>CPI Nowcasting Presentation</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

  @page {{
    size: 16in 9in;
    margin: 0;
  }}

  * {{
    box-sizing: border-box;
    margin: 0;
    padding: 0;
  }}

  body {{
    font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background-color: #0f172a;
    color: #1e293b;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }}

  .slide {{
    width: 16in;
    height: 9in;
    position: relative;
    page-break-after: always;
    break-after: page;
    background: #ffffff;
    display: flex;
    flex-direction: column;
    padding: 0.8in 1in;
    overflow: hidden;
  }}

  /* Slide 1 - Title Slide (Dark Theme) */
  .slide-title-bg {{
    background: radial-gradient(circle at 85% 15%, rgba(14, 165, 233, 0.15) 0%, transparent 50%),
                radial-gradient(circle at 15% 85%, rgba(16, 185, 129, 0.12) 0%, transparent 45%),
                #0b1329;
    color: #ffffff;
    justify-content: center;
    padding: 1in 1.2in;
  }}

  .badge {{
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 8px 18px;
    border-radius: 9999px;
    font-size: 15px;
    font-weight: 600;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    width: fit-content;
  }}

  .badge-cyan {{
    background: rgba(14, 165, 233, 0.15);
    border: 1px solid rgba(56, 189, 248, 0.4);
    color: #38bdf8;
  }}

  .title-main {{
    font-size: 52px;
    font-weight: 800;
    line-height: 1.15;
    margin-top: 24px;
    margin-bottom: 20px;
    letter-spacing: -0.02em;
    color: #ffffff;
  }}

  .title-sub {{
    font-size: 24px;
    font-weight: 400;
    color: #94a3b8;
    max-width: 900px;
    line-height: 1.5;
    margin-bottom: 48px;
  }}

  .author-card {{
    display: flex;
    align-items: center;
    gap: 24px;
    padding-top: 32px;
    border-top: 1px solid rgba(255, 255, 255, 0.12);
  }}

  .author-avatar {{
    width: 60px;
    height: 60px;
    border-radius: 50%;
    background: linear-gradient(135deg, #0ea5e9, #10b981);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 24px;
    font-weight: 700;
    color: #ffffff;
  }}

  .author-name {{
    font-size: 22px;
    font-weight: 700;
    color: #f8fafc;
  }}

  .author-role {{
    font-size: 16px;
    color: #64748b;
    margin-top: 4px;
  }}

  /* Standard Slide Header */
  .slide-header {{
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    margin-bottom: 36px;
    border-bottom: 2px solid #f1f5f9;
    padding-bottom: 18px;
  }}

  .slide-category {{
    font-size: 14px;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #0284c7;
    margin-bottom: 6px;
  }}

  .slide-title {{
    font-size: 38px;
    font-weight: 800;
    color: #0f172a;
    letter-spacing: -0.02em;
  }}

  .slide-number {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 18px;
    font-weight: 600;
    color: #94a3b8;
  }}

  /* Content Layouts */
  .grid-2 {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 36px;
    flex: 1;
    align-items: center;
  }}

  .grid-3 {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 28px;
    flex: 1;
    align-items: stretch;
  }}

  .card {{
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 16px;
    padding: 30px;
    display: flex;
    flex-direction: column;
  }}

  .card-highlight {{
    background: #f0f9ff;
    border: 1px solid #bae6fd;
  }}

  .card-accent {{
    background: #ecfdf5;
    border: 1px solid #a7f3d0;
  }}

  .card-icon {{
    width: 52px;
    height: 52px;
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 26px;
    margin-bottom: 20px;
  }}

  .icon-blue {{
    background: #e0f2fe;
    color: #0369a1;
  }}

  .icon-red {{
    background: #fee2e2;
    color: #b91c1c;
  }}

  .icon-green {{
    background: #d1fae5;
    color: #047857;
  }}

  .card-title {{
    font-size: 22px;
    font-weight: 700;
    color: #0f172a;
    margin-bottom: 12px;
  }}

  .card-desc {{
    font-size: 16px;
    line-height: 1.6;
    color: #475569;
  }}

  ul.feature-list {{
    list-style: none;
    margin-top: 14px;
  }}

  ul.feature-list li {{
    position: relative;
    padding-left: 26px;
    margin-bottom: 12px;
    font-size: 16px;
    line-height: 1.5;
    color: #334155;
  }}

  ul.feature-list li::before {{
    content: "•";
    position: absolute;
    left: 8px;
    color: #0ea5e9;
    font-size: 22px;
    line-height: 1;
  }}

  .img-frame {{
    border-radius: 14px;
    border: 1px solid #e2e8f0;
    box-shadow: 0 4px 20px -4px rgba(0, 0, 0, 0.06);
    width: 100%;
    max-height: 4.8in;
    object-fit: contain;
    background: #ffffff;
  }}

  /* Methodology Steps */
  .step-row {{
    display: flex;
    gap: 16px;
    margin-top: 20px;
  }}

  .step-pill {{
    flex: 1;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 16px 18px;
    border-top: 4px solid #0284c7;
  }}

  .step-pill-num {{
    font-size: 13px;
    font-weight: 700;
    color: #0284c7;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }}

  .step-pill-title {{
    font-size: 17px;
    font-weight: 700;
    color: #0f172a;
    margin: 6px 0;
  }}

  .step-pill-desc {{
    font-size: 13px;
    color: #64748b;
    line-height: 1.4;
  }}

  .footer-note {{
    margin-top: auto;
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 13px;
    color: #94a3b8;
    padding-top: 14px;
    border-top: 1px solid #f1f5f9;
  }}
</style>
</head>
<body>

  <!-- SLIDE 1: Title -->
  <div class="slide slide-title-bg">
    <div class="badge badge-cyan">Automated Price Intelligence</div>
    <div class="title-main">High-Frequency Inflation Nowcasting<br>via Automated Price Pipeline</div>
    <div class="title-sub">Turning online product prices into high-frequency CPI signals and real-time economic intelligence.</div>
    <div class="author-card">
      <div class="author-avatar">TK</div>
      <div>
        <div class="author-name">Taing Korngmeng</div>
        <div class="author-role">Data Engineering & Applied Macroeconomic Analytics • Cambodia CPI Pipeline</div>
      </div>
    </div>
  </div>

  <!-- SLIDE 2: Introduction -->
  <div class="slide">
    <div class="slide-header">
      <div>
        <div class="slide-category">Overview & Foundations</div>
        <div class="slide-title">Introduction: What is CPI & Why Does It Matter?</div>
      </div>
      <div class="slide-number">01 / 05</div>
    </div>

    <div class="grid-2">
      <div>
        <div class="card card-highlight" style="margin-bottom: 24px;">
          <div class="card-title" style="color: #0369a1;">Consumer Price Index (CPI) Defined</div>
          <p class="card-desc">
            A macroeconomic indicator that tracks the aggregate price of a fixed monthly <strong>"shopping basket"</strong> of consumer goods and services typically purchased by households across <strong>12 official COICOP categories</strong>.
          </p>
        </div>

        <div class="card">
          <div class="card-title">Why CPI Matters in the Real World:</div>
          <ul class="feature-list">
            <li><strong>Monetary Policy:</strong> Guides central bank interest rates and currency defense.</li>
            <li><strong>Purchasing Power & Cost of Living:</strong> Sets wage negotiations, pension adjustments, and public subsidies.</li>
            <li><strong>Planning & Real Contracts:</strong> Indexes commercial leases, government budgets, and supply chain agreements.</li>
          </ul>
        </div>
      </div>

      <div style="display: flex; flex-direction: column; align-items: center; justify-content: center;">
        <img src="{b64_img['basket']}" class="img-frame" alt="CPI Basket">
      </div>
    </div>

    <div class="footer-note">
      <span>Cambodia CPI Pipeline Project</span>
      <span>Taing Korngmeng</span>
    </div>
  </div>

  <!-- SLIDE 3: Problem Statement -->
  <div class="slide">
    <div class="slide-header">
      <div>
        <div class="slide-category">Challenges in Official Statistics</div>
        <div class="slide-title">Problem Statement: Limitations of Traditional CPI</div>
      </div>
      <div class="slide-number">02 / 05</div>
    </div>

    <div class="grid-3">
      <div class="card">
        <div class="card-icon icon-red">⏱️</div>
        <div class="card-title">Severe Time-Lag</div>
        <div class="card-desc">
          Official CPI statistics are published monthly or quarterly with a <strong>2 to 4-week delay</strong>. Decisions are made using outdated economic snapshots.
        </div>
        <ul class="feature-list" style="margin-top: 20px;">
          <li>Delayed response to sudden price shocks</li>
          <li>Slow detection of local commodity spikes</li>
        </ul>
      </div>

      <div class="card">
        <div class="card-icon icon-red">📉</div>
        <div class="card-title">Low Data Frequency</div>
        <div class="card-desc">
          Prices are collected once a month at discrete survey intervals, missing high-volatility shifts in essential items like fuel, meat, and fresh food.
        </div>
        <ul class="feature-list" style="margin-top: 20px;">
          <li>Lack of daily or weekly visibility</li>
          <li>No high-frequency intra-month trend indicators</li>
        </ul>
      </div>

      <div class="card">
        <div class="card-icon icon-red">💼</div>
        <div class="card-title">High Operational Friction</div>
        <div class="card-desc">
          Traditional CPI relies on labor-intensive manual price audits at brick-and-mortar stalls, which is expensive, difficult to scale, and prone to collection bias.
        </div>
        <ul class="feature-list" style="margin-top: 20px;">
          <li>High surveying and field cost</li>
          <li>Limited geographic and store coverage</li>
        </ul>
      </div>
    </div>

    <div class="footer-note">
      <span>Cambodia CPI Pipeline Project</span>
      <span>Taing Korngmeng</span>
    </div>
  </div>

  <!-- SLIDE 4: Objective -->
  <div class="slide">
    <div class="slide-header">
      <div>
        <div class="slide-category">Solution Strategy</div>
        <div class="slide-title">Project Objectives: Real-Time Inflation Intelligence</div>
      </div>
      <div class="slide-number">03 / 05</div>
    </div>

    <div class="grid-3">
      <div class="card card-accent">
        <div class="card-icon icon-green">🌐</div>
        <div class="card-title">1. Automated Ingestion</div>
        <div class="card-desc">
          Build a robust, automated daily data harvesting pipeline extracting live product prices, units, and categories across modern supermarkets and e-commerce outlets.
        </div>
      </div>

      <div class="card card-accent">
        <div class="card-icon icon-green">📊</div>
        <div class="card-title">2. COICOP Harmonization</div>
        <div class="card-desc">
          Standardize scraped products, normalize units (weight/volume), and map retail goods to international <strong>COICOP classifications</strong> to compute high-frequency price indices.
        </div>
      </div>

      <div class="card card-accent">
        <div class="card-icon icon-green">🎯</div>
        <div class="card-title">3. Nowcasting & Validation</div>
        <div class="card-desc">
          Deploy machine learning and time-series models to <strong>nowcast the official CPI</strong> weeks ahead of release, evaluating tracking error and residual bias.
        </div>
      </div>
    </div>

    <div style="margin-top: 28px;">
      <div class="card" style="background: #f1f5f9; padding: 22px 30px;">
        <div style="display: flex; align-items: center; justify-content: space-between;">
          <div>
            <div style="font-size: 18px; font-weight: 700; color: #0f172a;">Core Outcome</div>
            <div style="font-size: 15px; color: #475569; margin-top: 4px;">Empowering economists, policymakers, and business leaders with leading indicators rather than trailing post-mortems.</div>
          </div>
          <div class="badge badge-cyan" style="background: #0284c7; color: #ffffff; border: none;">Daily High-Frequency Signals</div>
        </div>
      </div>
    </div>

    <div class="footer-note">
      <span>Cambodia CPI Pipeline Project</span>
      <span>Taing Korngmeng</span>
    </div>
  </div>

  <!-- SLIDE 5: Methodology - Analytical Framework -->
  <div class="slide">
    <div class="slide-header">
      <div>
        <div class="slide-category">Analytical Pipeline</div>
        <div class="slide-title">Methodology: Web-Scraped Prices for Nowcasting</div>
      </div>
      <div class="slide-number">04 / 05</div>
    </div>

    <div style="display: flex; flex-direction: column; height: 100%;">
      <div style="text-align: center; margin-bottom: 24px;">
        <img src="{b64_img['framework']}" class="img-frame" style="max-height: 2.8in; border: none; box-shadow: none;" alt="Nowcasting Framework">
      </div>

      <div class="step-row">
        <div class="step-pill">
          <div class="step-pill-num">Step 1</div>
          <div class="step-pill-title">Collect</div>
          <div class="step-pill-desc">Supermarket websites, e-commerce, and APIs. Extract product name, price, unit, date, and outlet.</div>
        </div>
        <div class="step-pill">
          <div class="step-pill-num">Step 2</div>
          <div class="step-pill-title">Standardize</div>
          <div class="step-pill-desc">Data cleaning, product matching, unit normalization, and mapping into the 12 COICOP groups.</div>
        </div>
        <div class="step-pill">
          <div class="step-pill-num">Step 3</div>
          <div class="step-pill-title">Measure</div>
          <div class="step-pill-desc">Calculate daily & weekly high-frequency price indices by individual item and group level.</div>
        </div>
        <div class="step-pill">
          <div class="step-pill-num">Step 4</div>
          <div class="step-pill-title">Model</div>
          <div class="step-pill-desc">Machine Learning and time-series nowcasting models generate leading inflation signals.</div>
        </div>
        <div class="step-pill">
          <div class="step-pill-num">Step 5</div>
          <div class="step-pill-title">Benchmark</div>
          <div class="step-pill-desc">Validate nowcast accuracy against official monthly government CPI releases; optimize model weights.</div>
        </div>
      </div>

      <div class="footer-note">
        <span>Cambodia CPI Pipeline Project</span>
        <span>Taing Korngmeng</span>
      </div>
    </div>
  </div>

  <!-- SLIDE 6: Methodology - Technical Architecture -->
  <div class="slide">
    <div class="slide-header">
      <div>
        <div class="slide-category">Technical Implementation</div>
        <div class="slide-title">Methodology: End-to-End Data Pipeline Architecture</div>
      </div>
      <div class="slide-number">05 / 05</div>
    </div>

    <div class="grid-2" style="align-items: center;">
      <div>
        <div class="card" style="margin-bottom: 16px;">
          <div style="font-size: 18px; font-weight: 700; color: #0f172a; margin-bottom: 8px;">Orchestration & Infrastructure</div>
          <p class="card-desc"><strong>Apache Airflow</strong> schedules ingestion and transformation DAGs within a containerized <strong>Docker Compose</strong> stack.</p>
        </div>

        <div class="card" style="margin-bottom: 16px;">
          <div style="font-size: 18px; font-weight: 700; color: #0f172a; margin-bottom: 8px;">PostgreSQL Medallion Architecture</div>
          <ul class="feature-list" style="margin-top: 6px;">
            <li><strong>Bronze (Raw):</strong> Stores raw scraped payloads, API records, and CSVs.</li>
            <li><strong>Silver (Cleaned - dbt):</strong> Deduplicates, cleans, normalizes units, and staging models.</li>
            <li><strong>Gold (Marts - dbt):</strong> Curated star schema tables with dimension and fact models.</li>
          </ul>
        </div>

        <div class="card">
          <div style="font-size: 18px; font-weight: 700; color: #0f172a; margin-bottom: 8px;">Serving & Analytics Plane</div>
          <p class="card-desc"><strong>Metabase</strong> powers interactive BI dashboards tracking real-time inflation trends and price volatility across sectors.</p>
        </div>
      </div>

      <div style="text-align: center;">
        <img src="{b64_img['architecture']}" class="img-frame" alt="Architecture Diagram">
      </div>
    </div>

    <div class="footer-note">
      <span>Cambodia CPI Pipeline Project</span>
      <span>Taing Korngmeng</span>
    </div>
  </div>

</body>
</html>
"""

html_path = os.path.join(workspace, "presentation_slides.html")
pdf_path = os.path.join(workspace, "CPI_Nowcasting_Presentation.pdf")

with open(html_path, "w", encoding="utf-8") as f:
    f.write(html_content)

print(f"HTML saved to {html_path}")

edge_path = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
cmd = [
    edge_path,
    "--headless",
    "--disable-gpu",
    "--no-pdf-header-footer",
    f"--print-to-pdf={pdf_path}",
    html_path
]

print("Generating PDF with Edge headless...")
res = subprocess.run(cmd, capture_output=True, text=True)
if os.path.exists(pdf_path):
    size_mb = os.path.getsize(pdf_path) / (1024 * 1024)
    print(f"SUCCESS: Generated PDF at {pdf_path} ({size_mb:.2f} MB)")
else:
    print(f"ERROR: PDF was not generated. Returncode: {res.returncode}\nStderr: {res.stderr}")
