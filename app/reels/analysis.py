"""Heurísticas visuais, não reconhecimento de personagens/cenas. Memória limitada."""
import json
import math
from PIL import Image, ImageChops, ImageFilter, ImageStat
from .tools import executable, run, ReelError
from ..db import now_iso


def schema(library):
    with library.db.connect() as db:
        db.executescript('''CREATE TABLE IF NOT EXISTS reel_analysis (
            asset_id TEXT PRIMARY KEY,sha256 TEXT NOT NULL,metrics_json TEXT NOT NULL,created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS reel_usage (
            job_id TEXT NOT NULL,asset_id TEXT NOT NULL,start REAL NOT NULL,end REAL NOT NULL,
            created_at TEXT NOT NULL,PRIMARY KEY(job_id,asset_id,start));''')


def analyze(library, identifier):
    schema(library);asset=library.asset(identifier,'video');path=library.asset_path(asset,verify=True)
    duration=min(600,asset['metadata']['duration']);interval=max(.2,duration/60)
    raw=run([executable('ffmpeg'),'-nostdin','-v','error','-threads','1','-protocol_whitelist','file,pipe',
             '-i',path,'-t',str(duration),'-vf',f'fps={1/interval},scale=160:90,format=gray','-filter_threads','1',
             '-frames:v','60','-f','rawvideo','pipe:1'],timeout=90)
    size=160*90;previous=None;windows=[]
    for index in range(min(60,len(raw)//size)):
        image=Image.frombytes('L',(160,90),raw[index*size:(index+1)*size])
        intensity=ImageStat.Stat(image).mean[0]
        sharp=ImageStat.Stat(image.filter(ImageFilter.FIND_EDGES)).stddev[0]
        motion=ImageStat.Stat(ImageChops.difference(image,previous)).mean[0] if previous else 0
        thumb=list(image.resize((9,8)).getdata())
        bits=''.join('1' if thumb[y*9+x]>thumb[y*9+x+1] else '0' for y in range(8) for x in range(8))
        score=.45*min(1,sharp/45)+.25*min(1,motion/35)+.30*max(0,1-abs(intensity-127)/127)
        windows.append({'time':round(index*interval,3),'score':round(score,4),'sharpness':sharp,'motion':motion,
                        'exposure':intensity,'change':motion>35,'hash':f'{int(bits,2):016x}'})
        previous=image
    if not windows:raise ReelError('A análise não encontrou frames decodificáveis.')
    result={'method':'sampled_visual_heuristics','semantic_understanding':False,'samples':windows,'interval':interval,'sampled_until':duration}
    with library.db.connect() as db:
        db.execute('INSERT OR REPLACE INTO reel_analysis VALUES (?,?,?,?)',(identifier,asset['sha256'],json.dumps(result),now_iso()))
    return result


def metrics(library,identifier):
    schema(library)
    with library.db.connect() as db:
        row=db.execute('SELECT metrics_json FROM reel_analysis WHERE asset_id=?',(identifier,)).fetchone()
    return json.loads(row[0]) if row else None


def select(library, assets, frames, cut_frames, *, avoid_reuse=True):
    schema(library);used={a['id']:[] for a in assets};chosen={a['id']:[] for a in assets}
    with library.db.connect() as db:
        for row in db.execute('SELECT asset_id,start,end FROM reel_usage'):
            if row['asset_id'] in used:used[row['asset_id']].append((round(row['start']*30),round(row['end']*30)))
    candidates=[]
    for asset in assets:
        cap=math.floor(asset['metadata']['duration']*30)
        info=metrics(library,asset['id'])
        for start in range(0,cap,max(1,cut_frames)):
            end=min(cap,start+cut_frames)
            sample=min(info['samples'],key=lambda w:abs(w['time']-start/30)) if info else {'score':.5,'hash':''}
            repeated=any(max(start,a)<min(end,b) for a,b in used[asset['id']])
            candidates.append((sample['score']-(.35 if repeated else 0),asset['id'],start,end,sample['hash']))
    candidates.sort(reverse=True);cuts=[];hashes=[];remaining=frames
    while candidates:
        def priority(item):
            distance=min(((int(item[4] or '0',16)^int(h or '0',16)).bit_count()/64 for h in hashes),default=1)
            return item[0]-.20*(1-distance)
        best=max(range(len(candidates)),key=lambda i:priority(candidates[i]))
        score,identifier,start,end,visual=candidates.pop(best)
        forbidden=used[identifier] if avoid_reuse else []
        # Divide janelas nas bordas dos intervalos já usados, aproveitando sobras reais.
        segments=[(start,end)]
        for low,high in forbidden:
            segments=[part for a,b in segments for part in ((a,min(b,low)),(max(a,high),b)) if part[1]>part[0]]
        for low,high in segments:
            count=min(high-low,remaining)
            if count<=0:continue
            cuts.append({'asset_id':identifier,'source_start':low/30,'duration':count/30,'frames':count,
                         'score':round(score,4),'similar_visual':visual in hashes})
            hashes.append(visual);remaining-=count
            if remaining==0:return cuts
    raise ReelError('Não há trechos inéditos suficientes. Importe novas gravações ou permita reutilização explicitamente.')


def record_usage(library,job_id,cuts):
    schema(library)
    with library.db.connect() as db:
        for cut in cuts:
            db.execute('INSERT OR IGNORE INTO reel_usage VALUES (?,?,?,?,?)',(job_id,cut['asset_id'],cut['source_start'],cut['source_start']+cut['duration'],now_iso()))
