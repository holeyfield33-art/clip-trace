"""Cache Commons search metadata; selection is manual and precedes scoring."""
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'corpus/e1/discovery'
DEST.mkdir(parents=True, exist_ok=True)
QUERIES = {
    'speech': 'filetype:video interview',
    'podcast': 'filetype:video interview two people',
    'outdoor': 'filetype:video river forest',
    'night': 'filetype:video night city',
    'music': 'filetype:video musical performance',
    'sport': 'filetype:video football training',
    'broll': 'filetype:video aerial landscape',
    'animation': 'filetype:video animation blender',
    'gameplay': 'filetype:video supertuxkart gameplay',
    'screen': 'filetype:video software tutorial',
}
for category, query in QUERIES.items():
    path = DEST / (category + '.json')
    if path.exists():
        continue
    args = dict(action='query', generator='search', gsrsearch=query,
                gsrnamespace=6, gsrlimit=12, prop='imageinfo',
                iiprop='url|size|metadata|extmetadata', format='json')
    url = 'https://commons.wikimedia.org/w/api.php?' + urllib.parse.urlencode(args)
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'ClipTraceE1/1.0 scientific research'})
        with urllib.request.urlopen(req, timeout=40) as r:
            data = json.load(r)
        path.write_text(json.dumps(data, indent=2), encoding='utf-8')
        print(category, flush=True)
        for p in data.get('query', {}).get('pages', {}).values():
            i = p['imageinfo'][0]
            m = {x['name']: x['value'] for x in i.get('metadata', [])}
            license = i.get('extmetadata', {}).get('LicenseShortName', {}).get('value')
            print(p['pageid'], p['title'], round(i['size']/1e6, 1), m.get('length'), license, flush=True)
    except Exception as e:
        print(category, repr(e), flush=True)
    time.sleep(1)
