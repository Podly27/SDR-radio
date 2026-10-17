#!/usr/bin/python3
"""Replay the generated 90 kHz test fixture; no SDR and no production database.
This deliberately tests Q65 and JT65 sequentially on one recording and may
exceed a real-time minute. The production default alternates protocols.
"""
import argparse,datetime,json,os,subprocess,sys,tempfile,time
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import eme_common as common
from eme_worker import parse_log,jt65_audio,save
from ft_worker import parse_line
parser=argparse.ArgumentParser();parser.add_argument('fixture',type=Path);parser.add_argument('--jt65',choices=['B','C'],default='B');args=parser.parse_args()
fixture=args.fixture.resolve();native=Path(__file__).resolve().parents[1]/'eme-native/eme-m65'
config=common.validate(json.loads((Path(__file__).resolve().parents[1]/'eme-initial-config.json').read_text()))
started=time.monotonic()
with tempfile.TemporaryDirectory(prefix='eme-replay-') as temp,patch.object(common,'DATA',Path(temp)):
 root=Path(temp);(root/'wsjtx_dir.txt').write_text(str(root)+'\n')
 r=subprocess.run([str(native),args.jt65,'B','N','96000',config['callsign'],'JN99CN','0','90',str(fixture)],cwd=root,capture_output=True,text=True,timeout=90);r.check_returncode()
 db=common.connect();q=[];j=[]
 for line in (root/'map65_rx.log').read_text().splitlines():
  p=parse_log(line)
  if p:q.append(p);save(db,0,config,p)
 assert any(p['message']=='CQ W9XYZ EN37' for p in q),q
 candidates=[]
 for line in r.stdout.splitlines():
  f=line.split()
  if len(f)==3 and f[0]=='EME_JT_CANDIDATE':
   frequency=float(f[1])
   if not any(abs(frequency-old)<100 for old in candidates):candidates.append(frequency)
 for frequency in candidates[:3]:
  wav=root/'261016_1200.wav';dial=frequency-1500;jt65_audio(fixture,wav,432045000,dial)
  out=subprocess.run(['/usr/bin/jt9','--jt65','-b',args.jt65,'-p','60','-d','2','-L','1000','-H','2000','-f','1500','-F','100',str(wav)],cwd=root,capture_output=True,text=True,timeout=40,env=dict(os.environ,OMP_NUM_THREADS='1'))
  for line in out.stdout.splitlines():
   p=parse_line(line,'jt65'+args.jt65.lower())
   if p:p.update(frequency=round(dial+p['offset']-1270.46),mode='JT65',submode=args.jt65);j.append(p);save(db,0,config,p)
 expected='CQ W1AAA FN31' if args.jt65=='B' else 'CQ K2BBB FN32';assert any(p['message']==expected for p in j),j
 db.close();print(json.dumps({'test_only':True,'seconds':round(time.monotonic()-started,2),'q65':q,'jt65':j,'stored':common.history('')['total']},indent=2))
