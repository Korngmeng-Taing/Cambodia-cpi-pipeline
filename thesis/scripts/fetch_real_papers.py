import os
import sys
import requests

if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8', errors='backslashreplace')

out_dir = r"D:\CPI PIPELINE\thesis\papers\original_publications"
os.makedirs(out_dir, exist_ok=True)

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml,application/pdf;q=0.9,*/*;q=0.8'
}

download_list = [
    {
        'name': '01_Cavallo_Rigobon_2016_BPP_Online_Prices.pdf',
        'url': 'https://www.nber.org/system/files/working_papers/w22298/w22298.pdf',
        'title': 'Cavallo & Rigobon (2016) - NBER Working Paper w22298'
    },
    {
        'name': '02_Polidoro_et_al_2014_ISTAT_Web_Scraping.pdf',
        'url': 'https://unece.org/fileadmin/DAM/stats/documents/ece/ces/ge.22/2014/10_Italy_Web_scraping.pdf',
        'title': 'Polidoro et al. (2014/2015) - ISTAT / UNECE Technical Paper'
    },
    {
        'name': '03_Eurostat_2022_HICP_Practical_Guide_Web_Scraping.pdf',
        'url': 'https://ec.europa.eu/eurostat/documents/3859598/15456424/KS-GQ-22-013-EN-N.pdf',
        'title': 'Eurostat (2022) - Practical Guide on Web Scraping for HICP'
    },
    {
        'name': '04_Berki_et_al_2025_BERT_COICOP_Classification.pdf',
        'url': 'https://www.frontiersin.org/journals/artificial-intelligence/articles/10.3389/frai.2025.1520659/pdf',
        'title': 'Berki et al. (2025) - Frontiers in AI Full Manuscript'
    },
    {
        'name': '05_BIS_2024_Project_Spectrum_AI_Inflation.pdf',
        'url': 'https://www.bis.org/publ/othp86.pdf',
        'title': 'BIS Innovation Hub (2024) - Project Spectrum Official Report'
    },
    {
        'name': '08_Diewert_Fox_2018_Substitution_Bias_Scanner_Data.pdf',
        'url': 'https://www.nber.org/system/files/working_papers/w24546/w24546.pdf',
        'title': 'Diewert & Fox (2018/2020) - NBER Working Paper w24546'
    },
    {
        'name': '09_Chessa_2016_EURONA_Scanner_Data_Dutch_CPI.pdf',
        'url': 'https://ec.europa.eu/eurostat/documents/3859598/7760982/KS-GP-16-001-EN-N.pdf',
        'title': 'Chessa (2016) - EURONA Issue 1 (Official Eurostat PDF)'
    },
    {
        'name': '10_Macias_et_al_2021_Nowcasting_Food_Inflation.pdf',
        'url': 'https://www.nbp.pl/publikacje/materialy_i_studia/352_en.pdf',
        'title': 'Macias et al. (2021/2023) - NBP Working Paper 352'
    },
    {
        'name': '11_Medeiros_et_al_2019_ML_Inflation_Forecasting.pdf',
        'url': 'http://www.econ.puc-rio.br/uploads/adm/trabalhos/files/td672.pdf',
        'title': 'Medeiros et al. (2019/2021) - PUC-Rio Working Paper 672'
    }
]

print(f"Fetching real open-access academic publications to {out_dir}...")
for item in download_list:
    dest = os.path.join(out_dir, item['name'])
    if os.path.exists(dest) and os.path.getsize(dest) > 30000:
        print(f"  [EXISTS] {item['name']} ({os.path.getsize(dest) // 1024} KB)")
        continue
    print(f"  [DOWNLOADING] {item['title']}...")
    try:
        r = requests.get(item['url'], headers=headers, timeout=45, allow_redirects=True)
        if r.status_code == 200 and len(r.content) > 20000:
            with open(dest, 'wb') as f:
                f.write(r.content)
            print(f"    [SAVED] {item['name']} ({len(r.content) // 1024} KB)")
        else:
            print(f"    [FAILED] HTTP {r.status_code}, Size: {len(r.content)} bytes")
    except Exception as e:
        print(f"    [ERROR] {e}")

print("Finished downloading open-access papers.")
