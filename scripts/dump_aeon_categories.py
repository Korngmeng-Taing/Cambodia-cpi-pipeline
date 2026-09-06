import json
from scrapers.sources._common import _cffi_get
from scrapers.sources.aeon import AEON1_API, AEON3_API, AEON_HEADERS

def get_tree(api_url):
    r = _cffi_get(api_url, params={'page': 1, 'limit': 1}, headers=AEON_HEADERS, timeout=15)
    cats = r.json().get('filters', {}).get('categories', [])
    rows = []
    def walk(node, path):
        name = node.get('name') or ''
        nid = node.get('id')
        cur = path + [name]
        rows.append((nid, ' / '.join(cur)))
        for ch in node.get('children', []):
            walk(ch, cur)
    for c in cats:
        if c.get('id'):
            walk(c, [])
    return rows

with open('scripts/aeon1_categories.txt', 'w', encoding='utf-8') as f:
    for nid, path in get_tree(AEON1_API):
        f.write(f'{nid}\t{path}\n')

with open('scripts/aeon3_categories.txt', 'w', encoding='utf-8') as f:
    for nid, path in get_tree(AEON3_API):
        f.write(f'{nid}\t{path}\n')

print("Categories written successfully.")
