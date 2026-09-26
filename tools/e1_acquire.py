"""Acquire a fixed, licensed corpus without reading matcher results."""
import concurrent.futures
import hashlib
import json
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'corpus/e1'
# Original works are never shared across partitions. Related interview parts are avoided.
# id, partition, category, Wikimedia page id (None = self-created control)
SPECS = [
 ('S01','evaluation','talking_head',67541948),
 ('S02','development','two_person_podcast',172497374),
 ('S03','evaluation','gameplay',169220834),
 ('S04','calibration','software_screen_recording',153385295),
 ('S05','evaluation','outdoor_natural_motion',122842790),
 ('S06','calibration','low_light',115344735),
 ('S07','evaluation','presentation_slides',None),
 ('S08','development','stock_broll',154926275),
 ('S09','development','animation',182339199),
 ('S10','evaluation','music_heavy',87171613),
 ('S11','calibration','low_visual_high_audio',None),
 ('S12','evaluation','high_visual_audio_replacement',61277776),
 ('S13','calibration','news_broll',14761922),
 ('S14','development','vertical_talking_head',87945461),
 ('S15','evaluation','high_motion_sport',14761553),
 ('S16','evaluation','minimal_information',None),
 ('N01','development','two_person_podcast',142888871),
 ('N02','development','talking_head',152397191),
 ('N03','development','stock_broll',84809791),
 ('N04','development','animation',127853211),
 ('N05','development','common_intro_template',None),
 ('N06','development','similar_music_genre',184609193),
 ('N07','calibration','software_screen_recording',9979850),
 ('N08','calibration','software_screen_recording',117821605),
 ('N09','calibration','low_light',181219572),
 ('N10','calibration','news_broll',16058303),
 ('N11','calibration','same_transcript_new_speaker',None),
 ('N12','calibration','room_tone',None),
 ('N13','evaluation','talking_head',149284744),
 ('N14','evaluation','talking_head',146967456),
 ('N15','evaluation','same_game',152464937),
 ('N16','evaluation','outdoor_natural_motion',124765853),
 ('N17','evaluation','stock_broll',161729092),
 ('N18','evaluation','same_slide_template',None),
 ('N19','evaluation','similar_music_genre',196083057),
 ('N20','evaluation','high_motion_sport',70108681),
 ('N21','evaluation','common_meme_imagery',None),
 ('N22','evaluation','silence_common_sound_effects',None),
 ('N23','evaluation','semantic_recreation',None),
 ('N24','evaluation','shared_third_party_broll',199853129),
]

def digest(p):
    return hashlib.file_digest(p.open('rb'), 'sha256').hexdigest()

def run(args):
    r = subprocess.run(args, capture_output=True, timeout=300)
    if r.returncode:
        raise RuntimeError(r.stderr.decode(errors='replace')[-1800:])
    return r.stdout

def api(page):
    cache=DEST/f'api-{page}.json'
    if cache.exists(): return json.loads(cache.read_text(encoding='utf-8'))
    url = ('https://commons.wikimedia.org/w/api.php?action=query&pageids=' + str(page) +
           '&prop=videoinfo&viprop=url%7Cderivatives%7Csize%7Cextmetadata&format=json')
    req = urllib.request.Request(url, headers={'User-Agent':'ClipTraceE1/1.0 scientific research'})
    for attempt in range(4):
        try:
            data=json.load(urllib.request.urlopen(req, timeout=60))
            cache.write_text(json.dumps(data),encoding='utf-8')
            return data
        except urllib.error.HTTPError as e:
            if e.code!=429: raise
            time.sleep(max(60,int(e.headers.get('Retry-After','60'))))
    raise RuntimeError('Rate limit persists after four spaced attempts')

def acquire(spec):
    aid, part, category, page = spec
    base = dict(asset_id=aid, partition=part, category=category, role='source' if aid[0]=='S' else 'negative',
                identity_group=f'commons:{page}' if page else f'self-created:{aid}')
    if page is None:
        return base | dict(acquisition='self-created', license='CC0-1.0', status='pending_generation')
    meta_path = DEST / f'{aid}.provenance.json'
    if meta_path.exists():
        return json.loads(meta_path.read_text(encoding='utf-8'))
    data = api(page)
    vi = data['query']['pages'][str(page)]['videoinfo'][0]
    metadata = vi['extmetadata']
    license = metadata.get('LicenseShortName',{}).get('value','')
    if not any(x in license for x in ['CC BY', 'CC0', 'Public domain']):
        raise RuntimeError(f'Unqualified license: {license}')
    variants = [x for x in vi.get('derivatives',[]) if 'vp9' in x.get('transcodekey','') and x.get('height',0)>=480]
    choice = min(variants, key=lambda x: abs(x.get('height',720)-720)) if variants else dict(src=vi['url'],width=vi['width'],height=vi['height'])
    url = choice['src'].split('?')[0]
    # Retain exact acquired excerpt bytes, hash, metadata and remote original identity.
    download = DEST / f'{aid}.download.webm'
    partial=download.with_suffix('.partial')
    if download.exists() and download.stat().st_size<100000:
        download.replace(download.with_suffix('.failed-mux'))
        if partial.exists() and partial.stat().st_size>1000000: partial.replace(download)
    if not download.exists():
        # Byte prefix is sufficient for low-bitrate WebM acquisition; original identity remains full remote work.
        # Normalize only after verifying actual encoded output duration below.
        for attempt in range(4):
            try:
                req=urllib.request.Request(url,headers={'User-Agent':'ClipTraceE1/1.0 scientific research','Range':'bytes=0-12582911'})
                with urllib.request.urlopen(req,timeout=120) as r,partial.open('wb') as f:
                    remaining=12582912
                    while remaining>0 and (chunk:=r.read(min(1024*1024,remaining))):
                        f.write(chunk);remaining-=len(chunk)
                partial.replace(download)
                break
            except urllib.error.HTTPError as e:
                if e.code!=429: raise
                time.sleep(max(60,int(e.headers.get('Retry-After','60'))))
    info = json.loads(run(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(download)]))
    duration = float(info['format']['duration'])
    # At least 48 seconds required for all registered sources; negatives at least 30.
    need = 48 if aid[0]=='S' else 30
    if duration < need:
        raise RuntimeError(f'{aid} duration {duration} < {need}; do not loop material')
    start = 0.0
    has_audio = any(s['codec_type']=='audio' for s in info['streams'])
    out = DEST / f'{aid}.mp4'
    vf = 'fps=12,scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1'
    if aid=='S14':
        vf = 'fps=12,crop=ih*9/16:ih,scale=406:720,setsar=1'
    args = ['ffmpeg','-v','error','-y','-threads','1','-ss',str(start),'-i',str(download)]
    if not has_audio:
        args += ['-f','lavfi','-i','anullsrc=r=16000:cl=mono']
    args += ['-map','0:v:0','-map','0:a:0' if has_audio else '1:a:0','-t',str(min(48,duration-start)),
             '-vf',vf,'-c:v','libx264','-preset','ultrafast','-crf','21','-threads','1',
             '-c:a','aac','-ar','16000','-ac','1',str(out)]
    run(args)
    output_info=json.loads(run(['ffprobe','-v','error','-show_format','-of','json',str(out)]))
    output_duration=float(output_info['format']['duration'])
    if output_duration<need-.1: raise RuntimeError(f'{aid}: acquired prefix too short: {output_duration}')
    base |= dict(acquisition='Commons transcode/excerpt', source_page=vi['descriptionurl'], source_title=data['query']['pages'][str(page)]['title'],
                 download_url=url, download_sha256=digest(download), download_note='First 50 seconds acquired with FFmpeg stream copy; cached full downloads from initial pass also retained.', license=license,
                 license_url=metadata.get('LicenseUrl',{}).get('value'), attribution=metadata.get('Artist',{}).get('value'),
                 license_metadata=metadata, acquisition_width=choice.get('width'), acquisition_height=choice.get('height'),
                 original_excerpt_start_s=start, duration_s=min(48,duration-start), original_has_audio=has_audio,
                 audio_note='preserved' if has_audio else 'synthetic silence; no source waveform information',
                 normalization=vf, path=str(out.resolve()), sha256=digest(out), status='ready')
    meta_path.write_text(json.dumps(base,indent=2),encoding='utf-8')
    print(aid, 'ready', license, round(download.stat().st_size/1e6,1), flush=True)
    return base

if __name__=='__main__':
    DEST.mkdir(exist_ok=True,parents=True)
    rows=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        jobs={ex.submit(acquire,s):s for s in SPECS}
        for future in concurrent.futures.as_completed(jobs):
            spec=jobs[future]
            try: rows.append(future.result())
            except Exception as e:
                print(spec[0],repr(e),flush=True)
                rows.append(dict(asset_id=spec[0],status='failed',error=str(e)))
    (DEST/'acquisition.json').write_text(json.dumps(sorted(rows,key=lambda r:r['asset_id']),indent=2),encoding='utf-8')
