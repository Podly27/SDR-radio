"""Native CSDR FM receiver with phase-continuous software Doppler correction."""
import threading,time
from csdr.chain import Chain
from pycsdr.modules import Buffer,Convert,Shift,FirDecimate,FmDemod,DcBlock,NfmDeemphasis
from pycsdr.types import Format
RATE=240000
class Demodulator:
 def __init__(self,sink,voice=False):
  self.error=None;self.sink=sink;self.shift=Shift(0.0);self.input=Buffer(Format.COMPLEX_CHAR,524288);self.output=Buffer(Format.SHORT,96000);self.reader=self.output.getReader()
  workers=[Convert(Format.COMPLEX_CHAR,Format.COMPLEX_FLOAT),self.shift,FirDecimate(10,.015,.45),FmDemod(),DcBlock()]
  if voice:workers.append(NfmDeemphasis(24000))
  workers.append(Convert(Format.FLOAT,Format.SHORT));self.chain=Chain(workers);self.input_reader=self.input.getReader();self.chain.setWriter(self.output);self.chain.setReader(self.input_reader);self.thread=threading.Thread(target=self.read,daemon=True);self.thread.start()
 def read(self):
  try:
   while True:
    data=self.reader.read()
    if data is None:break
    self.sink(data.tobytes())
  except Exception as e:self.error=repr(e)
 def tune(self,doppler_hz):self.shift.setRate(-float(doppler_hz)/RATE)
 def feed(self,iq):
  if self.error:raise RuntimeError(self.error)
  deadline=time.monotonic()+2
  while True:
   try:self.input.write(iq);break
   except BufferError:
    if self.error or time.monotonic()>deadline:raise RuntimeError('FM DSP input stalled')
    time.sleep(.005)
 def close(self):
  self.chain.stop();self.reader.stop();self.thread.join(timeout=3)
  if self.thread.is_alive():raise RuntimeError('FM audio output did not stop')
