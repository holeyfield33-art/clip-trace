"""Self-created information controls and declared common-content composites."""
import json
import math
import subprocess
import wave
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from cliptrace_e1.e1_common import CORPUS,OUT,load,dump,sha,ffmpeg,encoder,probe

FONT=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',22)
SMALL=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',14)
TRANSCRIPT=('A river carries water through a changing landscape. We measure the flow each morning. '
 'The chart compares observations across four seasons. Similar ideas can be expressed by different speakers. '
 'A shared topic does not establish that one recording was copied from another. ')*4

def audio(aid):
    path=CORPUS/f'{aid}.wav'
    if path.exists(): return path
    seed=int(aid[1:])+(0 if aid[0]=='S' else 100)
    rng=np.random.default_rng(seed)
    sr=16000
    t=np.arange(sr*48)/sr
    x=np.zeros_like(t)
    if aid in ['S11','N11']:
        voice='Microsoft David Desktop' if aid=='S11' else 'Microsoft Zira Desktop'
        ps=("Add-Type -AssemblyName System.Speech; $speaker=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f"$speaker.SelectVoice('{voice}'); $speaker.Rate=0; $speaker.SetOutputToWaveFile('{path}'); "
            f"$speaker.Speak('{TRANSCRIPT}'); $speaker.Dispose()")
        subprocess.run(['powershell','-NoProfile','-Command',ps],check=True,capture_output=True)
        return path
    if aid not in ['S16','N22']:
        for n in range(96):
            lo=n*8000; hi=lo+8000
            tt=np.arange(8000)/sr
            f=220*2**(int(rng.choice([0,2,4,5,7,9,12]))/12)
            x[lo:hi]=.14*np.sin(2*np.pi*f*tt)*np.exp(-tt*4)+.05*np.sin(2*np.pi*f*1.5*tt)
        x+=rng.normal(0,.003,len(x))
    if aid=='N12': x=rng.normal(0,.007,len(x))
    if aid=='N22':
        for n in [5,15,25,35,45]:
            x[n*sr:n*sr+1600]=.15*np.sin(2*np.pi*880*np.arange(1600)/sr)
    with wave.open(str(path),'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(sr);w.writeframes((x*32767).astype('<i2').tobytes())
    return path

def frame(aid,t):
    seed=int(aid[1:])+(0 if aid[0]=='S' else 100)
    rng=np.random.default_rng(seed+int(t//6))
    im=Image.new('RGB',(640,360),(238,241,245));d=ImageDraw.Draw(im)
    if aid in ['S16','N12','N22']:
        return Image.new('RGB',(640,360),(30,30,30))
    if aid in ['S11','N11']:
        d.rectangle((0,0,640,65),fill=(25,38,60));d.text((30,20),'Landscape field notes',font=FONT,fill='white')
        d.text((50,160),'Audio field journal',font=FONT,fill=(50,60,70))
        return im
    # Shared generic template / meme: not distinctive authorship evidence.
    if aid in ['N05','N21'] or (aid in ['S07','N18'] and t<4):
        if aid in ['S07','N18','N21']:
            # Independently drawn evaluation-only artwork; the development N05
            # smile/title asset must not enter this connected content component.
            d.rectangle((0,0,640,360),fill=(12,39,46))
            d.polygon([(160,55),(240,110),(225,210),(110,235),(65,125)],fill=(34,185,153))
            d.polygon([(135,95),(185,125),(175,180),(120,175)],fill=(245,244,225))
            d.line((300,95,580,95),fill=(239,136,77),width=9)
            d.line((300,125,515,125),fill=(239,136,77),width=4)
            d.text((300,175),'FIELD JOURNAL',font=FONT,fill=(245,244,225))
            d.text((300,220),'Observations in motion',font=SMALL,fill=(34,185,153))
            return im
        d.rectangle((0,0,640,360),fill=(38,55,83))
        d.ellipse((245,75,395,225),fill=(245,193,48));d.ellipse((280,115,290,127),fill='black');d.ellipse((348,115,358,127),fill='black')
        d.arc((280,135,360,188),0,180,fill='black',width=4)
        d.text((205,267),'A new perspective',font=FONT,fill='white')
        return im
    d.rectangle((0,0,640,65),fill=(25,38,60));d.text((30,20),'River flow: seasonal observations',font=FONT,fill='white')
    d.text((35,85),f'Observation period {1+int(t//6)}',font=SMALL,fill=(40,45,55))
    vals=rng.integers(35,180,6)
    if aid=='N23':
        for j,v in enumerate(vals):
            d.ellipse((60+j*85,220-v/2,120+j*85,280-v/2),fill=(50,110+j*15,150))
    else:
        for j,v in enumerate(vals):
            x=50+j*90;d.rectangle((x,290-v,x+45,290),fill=(35,110+j*10,170))
            d.text((x,300),['Jan','Mar','May','Jul','Sep','Nov'][j],font=SMALL,fill='black')
        d.line((35,105,35,290,605,290),fill='black',width=2)
    d.ellipse((50+(t*19)%500,330,58+(t*19)%500,338),fill=(240,120,40))
    return im

def generate(row):
    aid=row['asset_id']; out=CORPUS/(f'{aid}.v2.mp4' if aid in ['S07','N18','N21'] else f'{aid}.mp4')
    if not out.exists():
        aud=audio(aid)
        cmd=['ffmpeg','-v','error','-y','-threads','1','-f','rawvideo','-pix_fmt','rgb24','-s','640x360','-r','12','-i','pipe:0','-i',str(aud),
             '-t','48','-vf','scale=1280:720',*encoder(21),str(out)]
        p=subprocess.Popen(cmd,stdin=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            for n in range(48*12): p.stdin.write(frame(aid,n/12).tobytes())
            p.stdin.close();err=p.stderr.read();p.wait()
            if p.returncode: raise RuntimeError(err.decode())
        finally:
            if p.poll() is None: p.kill()
    return row|dict(status='ready',duration_s=48,path=str(out.resolve()),sha256=sha(out),
                   original_has_audio=aid!='S16',audio_note='self-created synthetic waveform or silence',
                   provenance='tools/e1_controls.py; self-created diagrams, template, tones; Windows offline TTS for S11/N11',
                   transcript=TRANSCRIPT if aid in ['S11','N11'] else None,
                   voice=('Microsoft David Desktop' if aid=='S11' else 'Microsoft Zira Desktop') if aid in ['S11','N11'] else None)

def composite(row,donor,start=10,duration=6):
    aid=row['asset_id'];out=CORPUS/f'{aid}.common.mp4'
    if not out.exists():
        # Replace, rather than add, a declared interval with the same third-party B-roll.
        graph=(f'[0:v]trim=0:{start},setpts=PTS-STARTPTS[v0];[0:a]atrim=0:{start},asetpts=PTS-STARTPTS[a0];'
               f'[1:v]trim=0:{duration},setpts=PTS-STARTPTS,scale=1280:720[v1];[1:a]atrim=0:{duration},asetpts=PTS-STARTPTS[a1];'
               f'[0:v]trim=start={start+duration},setpts=PTS-STARTPTS[v2];[0:a]atrim=start={start+duration},asetpts=PTS-STARTPTS[a2];'
               '[v0][a0][v1][a1][v2][a2]concat=n=3:v=1:a=1[v][a]')
        ffmpeg(['-i',row['path'],'-i',donor['path'],'-filter_complex',graph,'-map','[v]','-map','[a]',*encoder(21),out])
    return row|dict(path=str(out.resolve()),sha256=sha(out),common_content=dict(donor=donor['asset_id'],source_interval_s=[start,start+duration],donor_interval_s=[0,duration]),
                   license_note='Composite retains both constituents attribution and share-alike terms; see donor provenance.')

if __name__=='__main__':
    rows=load(CORPUS/'acquisition.json')
    if any(r['status']=='failed' for r in rows): raise RuntimeError('Resolve acquisition failures first')
    rows=[generate(r) if r['status']=='pending_generation' else r for r in rows]
    donor=next(r for r in rows if r['asset_id']=='N24')
    rows=[composite(r,donor) if r['asset_id'] in ['S05','S12'] else r for r in rows]
    dump(OUT/'corpus-manifest.json',dict(version='E1.1',assets=rows,
         limitations=['Synthetic slide/template and audio controls; portrait talking-head is a crop, not native mobile capture.',
                     'Acquisition transcodes may be below 720p; upscaled registration does not add native spatial information.']))
    assignments={r['asset_id']:r['partition'] for r in rows}
    groups={}
    for r in rows:
        groups.setdefault(r['identity_group'],set()).add(r['partition'])
    assert all(len(v)==1 for v in groups.values())
    dump(OUT/'partition-manifest.json',dict(version='E1.1',assignments=assignments,
        identity_groups={r['asset_id']:r['identity_group'] for r in rows},
        rule='Preselected category-balanced identities; common-content connected components stay together.',
        common_content_components=[['S05','S12','N24'],['S07','N18','N21','N23'],['S11','N11']],
        registry_scope='Only registered sources in the active partition; evaluation fingerprint extraction and scoring occur after freeze. Acquisition and category/integrity QA precede freeze.'),immutable=True)
    print('Corpus and three-way partition materialized',flush=True)
