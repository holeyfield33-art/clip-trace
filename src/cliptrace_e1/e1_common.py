"""E1 immutable JSON, content addressing and execution helpers."""
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'results/e1'
CORPUS = ROOT / 'corpus/e1'

def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()

def dump(path, obj, immutable=False):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    text=json.dumps(obj,sort_keys=True,indent=2,allow_nan=False)+'\n'
    if immutable and path.exists() and path.read_text(encoding='utf-8')!=text:
        raise ValueError(f'Immutable artifact already exists: {path}')
    path.write_text(text,encoding='utf-8')
    digest=sha(path)
    path.with_name(path.name+'.sha256').write_text(digest+'\n',encoding='ascii')
    return digest

def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def verify(path):
    path=Path(path)
    if sha(path)!=path.with_name(path.name+'.sha256').read_text().strip():
        raise ValueError(f'Hash mismatch: {path}')
    return load(path)

def artifact(obj):
    data=json.dumps(obj,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    digest=hashlib.sha256(data).hexdigest()
    path=OUT/'artifacts'/digest[:2]/(digest+'.json')
    path.parent.mkdir(parents=True,exist_ok=True)
    if not path.exists(): path.write_bytes(data)
    return digest

def run(args,timeout=180):
    p=subprocess.run([str(a) for a in args],capture_output=True,timeout=timeout)
    if p.returncode: raise RuntimeError(p.stderr.decode(errors='replace')[-2000:])
    return p.stdout

def ffmpeg(args,timeout=180):
    return run(['ffmpeg','-hide_banner','-v','error','-y','-threads','1','-filter_threads','1','-filter_complex_threads','1',*args],timeout)

def probe(path):
    return json.loads(run(['ffprobe','-v','error','-show_format','-show_streams','-of','json',path]))

def encoder(crf=26,codec='libx264'):
    return ['-c:v',codec,*(['-preset','ultrafast','-crf',str(crf)] if codec=='libx264' else ['-q:v','8']),
            '-threads','1','-pix_fmt','yuv420p','-c:a','aac','-ar','16000','-ac','1']
