"""Locally runnable E1 candidates. Functions receive media/features, never truth."""
import json
import subprocess
import time
from pathlib import Path
import cv2
import numpy as np
from .e1_common import ROOT,OUT,ffmpeg,sha,artifact
from .visual.frame_hash import extract as baseline_visual,score_pair as baseline_visual_score,_phash_from_gray_bytes
from .audio.fingerprint import extract as baseline_audio,score_pair as baseline_audio_score

cv2.setNumThreads(1)
FPCALC=next((ROOT/'tools/chromaprint').rglob('fpcalc.exe'),None)
METHODS=['V-A','V-B','V-C','A-baseline','A-chromaprint']
CONFIG=dict(version='E1.1',sample_fps=1,decode_size=[320,180],orb_features=120,
            orb_fast_threshold=12,orb_ratio=.8,orb_distance=48,homography_ransac_px=4,
            min_homography_inliers=6,temporal_block_frames=3,speeds=[.75,1,1.25,1.5],
            ambiguity_margin=.05,stage1_topk=10,stage2='retrieved_only',
            audio_chromaprint_algorithm=2,baseline_sample_fps=1,baseline_max_frames=64)

def extract(path,work=None):
    path=Path(path);work=Path(work or OUT/'audio_tmp');work.mkdir(parents=True,exist_ok=True)
    start=time.perf_counter()
    v=baseline_visual(path,sample_fps=1,max_frames=64)
    a=baseline_audio(path,work_dir=work)
    # Retain output presentation timestamps, not invented frame numbers from the ground truth.
    p=subprocess.run(['ffmpeg','-hide_banner','-v','info','-threads','1','-filter_threads','1','-i',str(path),
        '-vf','fps=1,scale=320:180,format=gray,showinfo','-an','-f','rawvideo','-pix_fmt','gray','pipe:1'],capture_output=True,timeout=90)
    if p.returncode: raise RuntimeError(p.stderr.decode(errors='replace')[-1000:])
    import re
    pts=[float(x) for x in re.findall(r'\bn:\s*\d+.*?pts_time:([\d.e+-]+)',p.stderr.decode(errors='replace'))]
    frames=np.frombuffer(p.stdout,np.uint8).reshape(-1,180,320)
    if len(pts)!=len(frames): raise ValueError('Decode timestamp count mismatch')
    orb=cv2.ORB_create(nfeatures=120,fastThreshold=12)
    hashes=[];local=[]
    for f in frames:
        small=cv2.resize(f,(64,64),interpolation=cv2.INTER_AREA)
        hashes.append(_phash_from_gray_bytes(small.tobytes()))
        kp,desc=orb.detectAndCompute(f,None)
        local.append(dict(points=[[round(float(x.pt[0]),3),round(float(x.pt[1]),3)] for x in kp],
                          descriptors=desc.tolist() if desc is not None else []))
    cp=dict(status='unsupported',fingerprint=[],reason='fpcalc_unavailable')
    if FPCALC:
        p=subprocess.run([str(FPCALC),'-algorithm','2','-raw','-json',str(path)],capture_output=True,timeout=90)
        try:
            raw=json.loads(p.stdout)
            cp=dict(status='evaluated' if raw.get('fingerprint') else 'not_evaluated',
                    fingerprint=raw.get('fingerprint',[]),duration=raw.get('duration'),
                    returncode=p.returncode,stderr=p.stderr.decode(errors='replace').strip(),
                    reason=None if raw.get('fingerprint') else 'insufficient_audio_for_chromaprint')
        except ValueError:
            cp=dict(status='failed',fingerprint=[],reason=p.stderr.decode(errors='replace')[-500:])
    obj=dict(config=CONFIG,media_sha256=sha(path),duration_s=v['duration_s'],decode_pts_s=pts,
             timestamp_convention='FFmpeg fps=1 output PTS; selected original frame lies within the 1s sampling cell.',
             baseline_visual=v,baseline_audio=a,hashes=hashes,local=local,chromaprint=cp)
    return obj,dict(wall_s=time.perf_counter()-start)

def popcount(x):
    return np.bitwise_count(x)

def similarities(c,s):
    a=np.array([int(x,16) for x in c],dtype=np.uint64)
    b=np.array([int(x,16) for x in s],dtype=np.uint64)
    return np.maximum(0,1-popcount(a[:,None]^b[None,:]).astype(float)/32)

def merge_blocks(blocks):
    out=[]
    for block in blocks:
        if out and abs(out[-1]['source'][1]-block['source'][0])<=1.25 and abs(out[-1]['candidate'][1]-block['candidate'][0])<.01:
            out[-1]['source'][1]=max(out[-1]['source'][1],block['source'][1])
            out[-1]['candidate'][1]=block['candidate'][1]
        else: out.append(dict(source=list(block['source']),candidate=list(block['candidate'])))
    return out

def temporal(c,s):
    if not c['hashes'] or not s['hashes']: return dict(score=None,status='not_evaluated',blocks=[])
    sim=similarities(c['hashes'],s['hashes'])
    # Motion-sensitive sequence fingerprint: appearance plus XOR-change consistency.
    ch=np.array([int(x,16) for x in c['hashes']],np.uint64)
    sh=np.array([int(x,16) for x in s['hashes']],np.uint64)
    n,m=sim.shape;blocks=[];scores=[]
    for lo in range(0,n,3):
        hi=min(n,lo+3);length=hi-lo;best=(-1,None,None)
        for speed in CONFIG['speeds']:
            idx=np.rint(np.arange(length)*speed).astype(int)
            offsets=np.arange(max(0,m-int(idx[-1])))
            if not len(offsets): continue
            js=offsets[:,None]+idx[None,:]
            appearance=sim[np.arange(lo,hi)[None,:],js].mean(axis=1)
            if length>1:
                delta=popcount((ch[lo+1:hi]^ch[lo:hi-1])[None,:]^(sh[js[:,1:]]^sh[js[:,:-1]])).astype(float)
                score=.7*appearance+.3*np.maximum(0,1-delta/32).mean(axis=1)
            else: score=appearance
            k=int(score.argmax())
            if float(score[k])>best[0]: best=(float(score[k]),int(offsets[k]),speed)
        val,off,speed=best;scores.extend([max(0,val)]*length)
        if off is not None and val>=.55:
            blocks.append(dict(source=[float(off),min(s['duration_s'],off+length*speed)],
                               candidate=[float(lo),min(c['duration_s'],float(hi))]))
    info=min(1,max(0,len(set(c['hashes']))-1)/2)
    score=float(np.mean(scores))*info
    blocks=merge_blocks(blocks)
    return dict(score=score,status='evaluated',blocks=blocks,information_factor=info)

def orb_retrieve(c,s):
    # Coarse descriptor support only; no geometry or labels enter retrieval.
    cd=[np.asarray(f['descriptors'],np.uint8) for f in c['local'] if f['descriptors']]
    sd=[np.asarray(f['descriptors'],np.uint8) for f in s['local'] if f['descriptors']]
    if not cd or not sd: return 0.
    aa=np.concatenate(cd)[::3];bb=np.concatenate(sd)[::3]
    matches=cv2.BFMatcher(cv2.NORM_HAMMING).match(aa,bb)
    return sum(x.distance<=48 for x in matches)/len(aa)

def local_verify(c,s):
    valid=[(i,np.asarray(f['descriptors'],np.uint8)) for i,f in enumerate(s['local']) if f['descriptors']]
    if not valid: return dict(score=None,status='not_evaluated',blocks=[],reason='no_source_local_features')
    pooled=np.concatenate([d for _,d in valid]);owners=np.concatenate([np.full(len(d),i) for i,d in valid])
    bf=cv2.BFMatcher(cv2.NORM_HAMMING);pairs=[];scores=[]
    for i,cf in enumerate(c['local']):
        if not cf['descriptors']: scores.append(0.);continue
        cd=np.asarray(cf['descriptors'],np.uint8)
        match=bf.match(cd,pooled)
        counts=np.bincount([int(owners[x.trainIdx]) for x in match if x.distance<=48],minlength=len(s['local']))
        targets=np.argsort(-counts,kind='stable')[:3]
        best=(0.,None,0)
        for j in targets:
            sf=s['local'][int(j)]
            if len(sf['descriptors'])<6 or counts[j]<4: continue
            raw=bf.knnMatch(cd,np.asarray(sf['descriptors'],np.uint8),k=2)
            good=[a for pair in raw if len(pair)==2 for a,b in [pair] if a.distance<.8*b.distance and a.distance<=48]
            if len(good)<6: continue
            cp=np.float32([cf['points'][x.queryIdx] for x in good]);sp=np.float32([sf['points'][x.trainIdx] for x in good])
            cv2.setRNGSeed(1701)
            H,mask=cv2.findHomography(cp,sp,cv2.RANSAC,4.0,maxIters=500,confidence=.99)
            nin=int(mask.sum()) if mask is not None else 0
            if H is None or nin<6: continue
            # Require spatial extent, avoiding one tiny common logo claiming a whole work.
            pts=cp[mask.ravel().astype(bool)]
            extent=float(np.prod(np.ptp(pts,axis=0)))/(320*180)
            sc=min(1,nin/min(40,len(cd)))*min(1,extent/.08)
            if sc>best[0]: best=(sc,int(j),nin)
        score,j,nin=best;scores.append(score)
        if j is not None and score>=.15: pairs.append((i,j,score,nin))
    if not scores: return dict(score=None,status='not_evaluated',blocks=[],reason='no_candidate_local_features')
    blocks=[]
    for i,j,_,_ in pairs:
        block=dict(source=[float(j),min(s['duration_s'],float(j+1))],candidate=[float(i),min(c['duration_s'],float(i+1))])
        if blocks and 0 <= j-blocks[-1]['source'][1] <= 1 and i==blocks[-1]['candidate'][1]:
            blocks[-1]['source'][1]=block['source'][1];blocks[-1]['candidate'][1]=block['candidate'][1]
        else: blocks.append(block)
    return dict(score=float(np.mean(scores)),status='evaluated',blocks=blocks,
                matched_frames=len(pairs),geometric_inliers=sum(p[3] for p in pairs))

def chromaprint(c,s):
    ca=c['chromaprint'];sa=s['chromaprint']
    if not ca['fingerprint'] or not sa['fingerprint']:
        return dict(score=None,status='not_evaluated',reason=ca.get('reason') or sa.get('reason'),blocks=[])
    a=np.asarray(ca['fingerprint'],dtype=np.int64).astype(np.uint32)
    b=np.asarray(sa['fingerprint'],dtype=np.int64).astype(np.uint32)
    if len(a)>len(b): return dict(score=None,status='not_evaluated',reason='candidate_fingerprint_longer_than_source',blocks=[])
    # Constant/silent fingerprints convey no identity information.
    if len(np.unique(a))<2 or len(np.unique(b))<2: return dict(score=0.,status='evaluated',reason='uninformative_fingerprint',blocks=[])
    windows=np.lib.stride_tricks.sliding_window_view(b,len(a))
    scores=np.maximum(0,1-popcount(windows^a).astype(float).mean(axis=1)/16)
    best=int(scores.argmax())
    return dict(score=float(scores[best]),status='evaluated',offset_fingerprint_frames=best,blocks=[])

def coarse(method,c,s):
    if method=='V-A': return baseline_visual_score(c['baseline_visual'],s['baseline_visual']).get('score') or 0.
    if method=='V-B': return float(similarities(c['hashes'],s['hashes']).max(axis=1).mean()) if c['hashes'] and s['hashes'] else 0.
    if method=='V-C': return orb_retrieve(c,s)
    if method=='A-baseline': return baseline_audio_score(c['baseline_audio'],s['baseline_audio']).get('score') or 0.
    return chromaprint(c,s).get('score') or 0.

def pair(method,c,s):
    if method=='V-A':
        from .alignment.temporal import align_frame_hashes
        sc=baseline_visual_score(c['baseline_visual'],s['baseline_visual'])
        al=align_frame_hashes(c['baseline_visual']['frame_hashes'],s['baseline_visual']['frame_hashes'],sample_fps=1)
        return dict(score=sc.get('score'),status='evaluated' if sc.get('score') is not None else 'not_evaluated',
                    blocks=[dict(source=a,candidate=b) for a,b in zip(al['source_intervals_s'],al['candidate_intervals_s'])])
    if method=='V-B': return temporal(c,s)
    if method=='V-C': return local_verify(c,s)
    if method=='A-baseline':
        sc=baseline_audio_score(c['baseline_audio'],s['baseline_audio'])
        return dict(score=sc.get('score'),status='evaluated' if sc.get('score') is not None else 'not_evaluated',blocks=[])
    return chromaprint(c,s)

def match(c,registry):
    result={}
    for method in METHODS:
        ranked=sorted([(sid,coarse(method,c,s)) for sid,s in registry.items()],key=lambda r:(-r[1],r[0]))
        verified=[dict(parent=sid,**pair(method,c,registry[sid])) for sid,_ in ranked[:CONFIG['stage1_topk']]]
        verified.sort(key=lambda r:(-(r['score'] if r['score'] is not None else -1),r['parent']))
        top=verified[0] if verified else {}
        sc=top.get('score');second=verified[1].get('score') if len(verified)>1 else None
        result[method]=dict(retrieval=ranked,pairs=verified,top_parent=top.get('parent'),score=sc,
                            margin=sc-second if sc is not None and second is not None else None,
                            status='evaluated' if sc is not None else 'not_evaluated')
    return result
