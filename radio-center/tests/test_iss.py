"""Image framing/storage tests; native audio replay is a separate integration test."""
import io,sqlite3,struct,sys,tempfile,unittest
from unittest.mock import patch
from pathlib import Path
from contextlib import closing
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
from iss_worker import Frames

def bmp(width=4,height=4):
 pixels=b'\x00\x00\xff'*width*height
 return struct.pack('<2sIHHI',b'BM',54+len(pixels),95,0,54)+struct.pack('<IiiHHIIiiII',40,width,-height,1,24,0,len(pixels),0,0,0,0)+pixels
class FramesTest(unittest.TestCase):
 def test_fragmented_full_image_and_colour(self):
  with tempfile.TemporaryDirectory() as td:
   frames=Frames(td);data=b'junk [VIS detected]'+bmp()
   for i in range(0,len(data),7):frames.feed(data[i:i+7])
   self.assertEqual(frames.count,1)
   with closing(sqlite3.connect(Path(td)/'iss.sqlite')) as db:row=db.execute('SELECT filename,complete,mode,lines FROM images').fetchone()
   self.assertEqual(row[1:],(1,'PD 120',4))
   with Image.open(Path(td)/'iss-images'/row[0]) as image:self.assertEqual(image.getpixel((0,0)),(255,0,0))
 def test_partial_saved_and_distinguished(self):
  with tempfile.TemporaryDirectory() as td:
   f=Frames(td);f.feed(bmp()[:54+24]);f.finish()
   with closing(sqlite3.connect(Path(td)/'iss.sqlite')) as db:self.assertEqual(db.execute('SELECT complete,lines FROM images').fetchone(),(0,2))
 def test_native_early_finish_marker_preserves_partial(self):
  with tempfile.TemporaryDirectory() as td:
   f=Frames(td);f.feed(bmp()[:54+12]);f.feed(b' [FINISH-FRAME]')
   with closing(sqlite3.connect(Path(td)/'iss.sqlite')) as db:self.assertEqual(db.execute('SELECT complete,lines FROM images').fetchone(),(0,1))
 def test_history_pagination(self):
  import server
  with tempfile.TemporaryDirectory() as td:
   f=Frames(td);f.feed(bmp())
   with closing(sqlite3.connect(Path(td)/'iss.sqlite')) as db:
    for i in range(25):db.execute("INSERT INTO images(received,started,filename,mode,width,height,lines,complete,frequency) VALUES(?,?,?,?,?,?,?,?,?)",('2026-10-17T00:00:00+00:00','2026-10-17T00:00:00+00:00',str(i)+'.png','PD 120',640,496,496,1,145800000))
    db.commit()
   with patch.object(server,'DATA',Path(td)):
    page=server.iss_history('');older=server.iss_history('before='+str(page['next_before']))
    self.assertEqual(page['total'],26);self.assertEqual(len(page['events']),24);self.assertEqual(len(older['events']),2)
    self.assertFalse({r['id'] for r in page['events']}&{r['id'] for r in older['events']})
    with self.assertRaises(ValueError):server.iss_history('before=-1')
 def test_malformed_and_empty_not_saved(self):
  with tempfile.TemporaryDirectory() as td:
   f=Frames(td);f.feed(b'BM'+b'\xff'*100);f.finish();self.assertEqual(f.count,0)
if __name__=='__main__':unittest.main()
