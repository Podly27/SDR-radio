import sys,time,wave,subprocess,numpy as np
from pathlib import Path
sys.path.insert(0,'radio-center')
from iss_dsp import Demodulator
from iss_receiver import packet_command
p=Path('/tmp/iss-test-direwolf.conf');p.write_text('ADEVICE stdin null\nARATE 24000\nACHANNELS 1\nCHANNEL 0\nMYCALL N0CALL\nMODEM 1200\nFIX_BITS 0\nAGWPORT 0\nKISSPORT 0\n')
packet=subprocess.Popen(packet_command(p),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=0)
dsp=Demodulator(lambda pcm:packet.stdin.write(pcm));dsp.tune(10000);phase0=0
try:
 with wave.open('/tmp/iss-test-packet.wav') as wav:
  while pcm:=wav.readframes(2400):
   a=np.frombuffer(pcm,dtype='<i2').astype(float)/32768;phase=phase0+2*np.pi*np.cumsum(10000+np.repeat(a,10)*5000)/240000;phase0=float(phase[-1]%(2*np.pi));x=np.exp(1j*phase)*90;dsp.feed(np.column_stack([x.real+127.5,x.imag+127.5]).astype('uint8').tobytes());time.sleep(.1)
 time.sleep(.2)
finally:
 dsp.close();packet.stdin.close();packet.stdin=None
 stdout,stderr=packet.communicate(timeout=5)
 print(stdout.decode(errors='replace')[-1300:]);assert b'ISS SYNTHETIC PACKET TEST' in stdout
print('Synthetic UHF Doppler + FM + native AX.25 decode: OK')
