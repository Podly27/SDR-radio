"""Native WSJT-X synthetic signal checks; never accesses the SDR or live history."""
import sys,tempfile,subprocess,os,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ft_worker import decoder_command,parse_line
for period in (15,30,60,120,300):
 for sub in ('A','B'):
  mode=f'q65-{period}{sub.lower()}'
  with tempfile.TemporaryDirectory(prefix='weak-fixture-') as td:
   subprocess.run(['/usr/bin/q65sim','CQ K1ABC FN42',sub,'1500','0','0','0','1',str(period),'1','1','-10'],cwd=td,capture_output=True,check=True,timeout=20)
   path=next(Path(td).glob('*.wav'));start=time.monotonic()
   r=subprocess.run(decoder_command(mode,period,path),cwd=td,capture_output=True,text=True,timeout=55,env=dict(os.environ,OMP_NUM_THREADS='1'))
   parsed=[p for l in r.stdout.splitlines() if (p:=parse_line(l,mode))]
   assert any(p['message']=='CQ K1ABC FN42' for p in parsed),(mode,r.stdout,r.stderr)
   print(mode,': OK',round(time.monotonic()-start,2),'s',flush=True)
for sub in ('A','B','C'):
 mode='jt65'+sub.lower()
 with tempfile.TemporaryDirectory(prefix='weak-fixture-') as td:
  subprocess.run(['/usr/bin/jt65sim','-m',sub,'-n','1','-s','\\-10'],cwd=td,capture_output=True,check=True,timeout=20)
  r=subprocess.run(decoder_command(mode,60,next(Path(td).glob('*.wav'))),cwd=td,capture_output=True,text=True,timeout=55,env=dict(os.environ,OMP_NUM_THREADS='1'))
  parsed=[p for l in r.stdout.splitlines() if (p:=parse_line(l,mode))]
  assert any('K1ABC W9XYZ EN37' in p['message'] for p in parsed),(mode,r.stdout,r.stderr)
  print(mode,': OK',flush=True)
