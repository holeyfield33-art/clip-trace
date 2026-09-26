"""Fixed fractional design, truthful media generation and pre-run resource checkpoint."""
import concurrent.futures
import math
import os
import platform
import shutil
import time
import psutil
from .e1_common import ROOT,OUT,CORPUS,dump,load,verify,sha,ffmpeg,encoder,probe,run

LENGTHS=[1,2,3,5,10,15,30]
ANCHORS=['trim','h264_q35','crop25','speed125','audio_replace','subtitles']
ROTATING=['h264_q18','h264_q42','mpeg4','scale720','scale480','scale360','crop10','crop40','crop60',
 'offcenter25','mirror','rotate5','rotate15','perspective','letterbox','speed075','speed150',
 'reordered','discontinuous','frame_insert_delete','logo','central_text','picture_in_picture','reaction_layout',
 'audio_offset','pitch_up2','music_overlay','noise_compression','silence_insertion',
 'screen_recording','film_monitor','upscale_lanczos','frame_interpolation','denoise']

def attributes(name):
    family=('AUDIO' if name.startswith(('audio','pitch','music','noise','silence')) else
            'TEMPORAL' if name.startswith(('speed','reordered','discontinuous','frame_','trim')) and name!='frame_interpolation' else
            'OVERLAY' if name in ['subtitles','logo','central_text','picture_in_picture','reaction_layout'] else
            'CAPTURE' if name in ['screen_recording','film_monitor'] else
            'AI_LIGHT' if name in ['upscale_lanczos','frame_interpolation','denoise'] else
            'TRANSCODING' if name.startswith(('h264','mpeg4','scale')) else 'GEOMETRY')
    return dict(family=family,severity='harsh' if name in ['crop60','h264_q42','reordered','discontinuous','central_text','reaction_layout'] else 'moderate')

def design():
    corpus=verify(OUT/'corpus-manifest.json')['assets'];verify(OUT/'partition-manifest.json')
    rows=[]
    for asset in corpus:
        for li,length in enumerate(LENGTHS):
            names=ANCHORS+[ROTATING[(int(asset['asset_id'][1:])*7+li*6+j)%len(ROTATING)] for j in range(6)] if asset['role']=='source' else ['negative_excerpt']
            for name in names:
                speed={'speed075':.75,'speed125':1.25,'speed150':1.5}.get(name,1)
                start=2.0 if asset['role']=='source' else 0.
                source_intervals=[[start,start+length*speed]]
                maps=[dict(candidate=[0.,float(length)],source=source_intervals[0])]
                if name in ['reordered','discontinuous']:
                    half=length/2
                    iv=[[2.,2.+half],[26.,26.+half]] if name=='discontinuous' else [[4.+half,4.+length],[2.,2.+half]]
                    source_intervals=iv;maps=[dict(candidate=[i*half,(i+1)*half],source=x) for i,x in enumerate(iv)]
                cid=f'E{len(rows)+1:05d}'
                shared=asset['asset_id']=='N24'
                rows.append(dict(candidate_id=cid,identity=asset['asset_id'],partition=asset['partition'],
                    category=asset['category'],role=asset['role'],length_s=length,transform=name,
                    **attributes(name),speed=speed,source_intervals_s=source_intervals if asset['role']=='source' else [],
                    frame_mapping=maps if asset['role']=='source' else [],
                    visual_ancestry=asset['role']=='source',audio_ancestry=asset['role']=='source' and name!='audio_replace' and not (name=='audio_offset' and length<=1.5),
                    expected_parent=asset['asset_id'] if asset['role']=='source' else None,
                    expected_ambiguity=shared or asset['asset_id'] in ['N18','N21'],
                    common_content_note='Contains identical third-party/template pixels; unique work ancestry must not be inferred.' if shared or asset['asset_id'] in ['N18','N21'] else None,
                    path=str((OUT/'candidates'/f'{cid}.mp4').resolve()),
                    interactions=[name,'H264 CRF26','AAC mono16k'] if name not in ['h264_q35','h264_q18','h264_q42','mpeg4'] else [name,'AAC mono16k']))
    assert len(rows)==1512
    return dict(version='E1.1',allocation='16 sources x 7 lengths x 12 fractional chains + 24 negatives x 7 lengths',
        design_rule='Six fixed anchors plus six rotating single-family transforms; all also encoded. No Cartesian cross-family design.',
        requested_lengths_s=LENGTHS,unmeasured_interactions=['arbitrary crop+speed+overlay combinations'],
        recipes=dict(anchors=ANCHORS,rotating=ROTATING,unsupported=['screen_recording','film_monitor']),candidates=rows)

def generate_one(row,assets):
    started=time.perf_counter();out=row['path'];name=row['transform'];length=row['length_s'];src=assets[row['identity']]['path']
    result=row|dict(status='not_evaluated',sha256=None)
    if name in ['screen_recording','film_monitor']:
        return result|dict(status='unsupported',reason='No authorized native capture surface / physical camera; no simulation mislabeled as capture.',wall_s=0.)
    try:
        vf=[];af=[];speed=row['speed'];start=2 if row['role']=='source' else 0
        args=['-ss',str(start),'-i',src]
        if name in ['reordered','discontinuous']:
            args=['-i',src];graph=[]
            for k,(a,b) in enumerate(row['source_intervals_s']):
                graph += [f'[0:v]trim=start={a}:end={b},setpts=PTS-STARTPTS[v{k}]',f'[0:a]atrim=start={a}:end={b},asetpts=PTS-STARTPTS[a{k}]']
            graph += ['[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]']
            args += ['-filter_complex',';'.join(graph),'-map','[v]','-map','[a]']
        else:
            if name.startswith('crop') or name=='offcenter25':
                pct=25 if name=='offcenter25' else int(name[4:]);keep=1-pct/100
                vf.append(f'crop=trunc(iw*{keep}/2)*2:trunc(ih*{keep}/2)*2'+(':0:0' if name=='offcenter25' else ''))
            if name=='mirror': vf.append('hflip')
            if name.startswith('rotate'): vf.append(f'rotate={int(name[6:])*math.pi/180}:fillcolor=black')
            if name=='perspective': vf.append('perspective=x0=20:y0=10:x1=W-10:y1=20:x2=0:y2=H-20:x3=W:y3=H')
            if name=='letterbox': vf.append('pad=iw:ih+120:0:60:black')
            if name.startswith('scale'): vf.append(f'scale=-2:{name[5:]}')
            if speed!=1: vf.append(f'setpts=PTS/{speed}');af.append(f'atempo={speed}')
            if name=='frame_insert_delete': vf.append('shuffleframes=0 0 2 3')
            if name=='subtitles': vf.append("drawtext=text='A conversation about the changing world':fontsize=28:fontcolor=white:borderw=3:x=(w-text_w)/2:y=h-65")
            if name=='logo': vf.append("drawbox=x=20:y=20:w=150:h=70:color=blue@0.8:t=fill,drawtext=text='CHANNEL':fontsize=22:fontcolor=white:x=28:y=40")
            if name=='central_text': vf.append("drawbox=x=iw/4:y=ih/3:w=iw/2:h=ih/3:color=black@0.9:t=fill,drawtext=text='WATCH THIS':fontsize=42:fontcolor=white:x=(w-text_w)/2:y=h/2")
            if name in ['picture_in_picture','reaction_layout']:
                scale=.7 if name=='picture_in_picture' else .5
                # Declared graphic host panel; source is geometrically reduced within a new canvas.
                vf += [f'scale=trunc(iw*{scale}/2)*2:trunc(ih*{scale}/2)*2',
                       'pad=1280:720:ow-iw:oh-ih:0x182030',"drawtext=text='Reaction panel':fontsize=30:fontcolor=white:x=20:y=40"]
            if name=='audio_replace':
                args += ['-f','lavfi','-i',f'anoisesrc=color=pink:amplitude=0.15:seed={int(row["candidate_id"][1:])}:r=16000:d={length}']
                args += ['-map','0:v','-map','1:a']
            elif name=='music_overlay':
                args += ['-f','lavfi','-i',f'aevalsrc=0.15*sin(2*PI*330*t)+0.1*sin(2*PI*440*t):s=16000:d={length}',
                         '-filter_complex','[0:a][1:a]amix=inputs=2:duration=first:normalize=0[a]','-map','0:v','-map','[a]']
            elif name=='noise_compression':
                args += ['-f','lavfi','-i',f'anoisesrc=color=white:amplitude=0.025:seed={int(row["candidate_id"][1:])}:r=16000:d={length}',
                         '-filter_complex','[0:a][1:a]amix=inputs=2:duration=first:normalize=0,acompressor=threshold=0.1:ratio=4[a]','-map','0:v','-map','[a]']
            elif name=='silence_insertion':
                args += ['-filter_complex','[0:a]asplit=2[x][y];[x]atrim=0:1,asetpts=PTS-STARTPTS[a0];anullsrc=r=16000:cl=mono,atrim=0:1[a1];[y]atrim=start=1,asetpts=PTS-STARTPTS[a2];[a0][a1][a2]concat=n=3:v=0:a=1[a]',
                         '-map','0:v','-map','[a]']
            else: args += ['-map','0:v','-map','0:a']
            if name=='audio_offset': af.append('adelay=1500')
            if name=='pitch_up2': af.append(f'asetrate=16000*{2**(2/12)},aresample=16000,atempo={2**(-2/12)}')
            if name=='upscale_lanczos': vf.append('scale=iw/2:ih/2,scale=iw*2:ih*2:flags=lanczos')
            if name=='frame_interpolation': vf.append('minterpolate=fps=24:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1')
            if name=='denoise': vf.append('hqdn3d=4:3:6:4.5')
            if vf:
                video_filter=','.join(vf).replace('drawtext=',"drawtext=fontfile='C\\:/Windows/Fonts/arial.ttf':")
                args += ['-vf',video_filter]
            if af: args += ['-af',','.join(af)]
        crf=int(name[6:]) if name.startswith('h264_q') else 26
        args += ['-t',str(length),*encoder(crf,'mpeg4' if name=='mpeg4' else 'libx264'),out]
        from pathlib import Path
        Path(out).parent.mkdir(parents=True,exist_ok=True)
        ffmpeg(args,timeout=300)
        info=probe(out);actual=float(info['format']['duration'])
        if abs(actual-length)>.3: raise ValueError(f'Duration mismatch: requested {length}, actual {actual}')
        if name=='frame_insert_delete':
            # At 12 fps, frame 1 in each block of four is replaced by frame 0.
            result['frame_mapping']=[dict(candidate=[i/12,min(length,(i+1)/12)],
                 source=[2+(i-(1 if i%4==1 else 0))/12,2+(i-(1 if i%4==1 else 0)+1)/12]) for i in range(length*12)]
            result['source_intervals_s']=[m['source'] for m in result['frame_mapping']]
        result |= dict(status='evaluated',sha256=sha(out),actual_duration_s=actual,size_bytes=int(info['format']['size']),
                       generation_command=['ffmpeg',*map(str,args)],wall_s=time.perf_counter()-started)
        result.pop('error',None)
    except Exception as e: result |= dict(status='failed',error=str(e),wall_s=time.perf_counter()-started)
    return result

def resource_checkpoint(manifest):
    q0=load(next((ROOT/'results/q0/runs').glob('*/run_meta.json')))
    n=len(manifest['candidates']);q0_media=list((ROOT/'results/q0/candidates').glob('*.mp4'))
    mean_bytes=sum(p.stat().st_size for p in q0_media)/max(1,len(q0_media))
    q0_seconds=q0['run_wall_s']/q0['n_ok']
    # Explicit conservative multipliers for 720p, 5 candidate algorithms, longer clips and repeat subset.
    estimate=dict(candidate_count=n,q0_matching_s_per_candidate=q0_seconds,
       q0_mean_candidate_bytes=mean_bytes,q0_rss_kb=q0['max_rss_kb'],
       expected_storage_bytes=max(8_000_000_000,n*mean_bytes*12),
       expected_cpu_hours=n*q0_seconds*5/3600+2,
       expected_peak_ram_bytes=6_000_000_000,expected_artifact_bytes=1_500_000_000,
       assumptions='5x Q0 matching allowance plus 2 CPU-hours generation; media multiplier12; not measured CPU time from Q0.',
       q0_cpu_measurement='unavailable; Q0 recorded wall time only')
    available=dict(logical_cpus=os.cpu_count(),ram_bytes=psutil.virtual_memory().total,
                   available_ram_bytes=psutil.virtual_memory().available,free_disk_bytes=shutil.disk_usage(ROOT).free)
    boundary=dict(max_storage_bytes=16_000_000_000,max_peak_ram_bytes=8_000_000_000,
                  estimated_cpu_budget_hours=18,workers=2,reserved_disk_bytes=10_000_000_000)
    fits=estimate['expected_storage_bytes']<min(boundary['max_storage_bytes'],available['free_disk_bytes']-boundary['reserved_disk_bytes']) and estimate['expected_cpu_hours']<18
    if not fits: raise RuntimeError('Design exceeds predeclared boundary; revise before generation/scoring')
    dump(OUT/'resource-checkpoint.json',dict(estimate=estimate,available=available,boundary=boundary,design_reduction=None,decision='proceed'),immutable=True)

def prepare():
    manifest=design();resource_checkpoint(manifest)
    dump(OUT/'transformation-manifest.json',manifest,immutable=True)
    environment=dict(platform=platform.platform(),python=platform.python_version(),ffmpeg=run(['ffmpeg','-version']).decode().splitlines()[0],
                     ffprobe=run(['ffprobe','-version']).decode().splitlines()[0],packages=load_packages(),
                     baseline_commit=run(['git','rev-parse','HEAD']).decode().strip(),
                     source_tree_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted((ROOT/'src').rglob('*.py'))},
                     tools_sha256={str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'tools/chromaprint').rglob('fpcalc.exe')})
    dump(OUT/'environment.json',environment)
    rows=manifest['candidates'];assets={x['asset_id']:x for x in verify(OUT/'corpus-manifest.json')['assets']}
    journal=OUT/'generation-results.jsonl';completed={}
    if journal.exists():
        import json
        completed={r['candidate_id']:r for r in map(json.loads,journal.read_text().splitlines())}
    started=time.perf_counter()
    with journal.open('a',encoding='utf-8') as f,concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        import json
        jobs={ex.submit(generate_one,r,assets):r for r in rows if r['candidate_id'] not in completed}
        for future in concurrent.futures.as_completed(jobs):
            r=future.result();completed[r['candidate_id']]=r
            f.write(json.dumps(r,sort_keys=True)+'\n');f.flush()
            if len(completed)%25==0: print('generated',len(completed),'/',len(rows),'elapsed',round(time.perf_counter()-started),flush=True)
    dump(OUT/'ground-truth.json',dict(version='E1.1',records=[completed[r['candidate_id']] for r in rows]),immutable=True)

def load_packages():
    import importlib.metadata
    return {x:importlib.metadata.version(x) for x in ['numpy','Pillow','opencv-python-headless','scipy','psutil','pytest']}

if __name__=='__main__': prepare()
