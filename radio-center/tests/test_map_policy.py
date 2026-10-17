"""Map tiles must be permitted by the dashboard's actual response policy."""
import ast,re,unittest
from pathlib import Path
from urllib.parse import urlsplit
ROOT=Path(__file__).resolve().parents[1]
class MapPolicy(unittest.TestCase):
 def test_leaflet_tile_origins_allowed_by_csp(self):
  tree=ast.parse((ROOT/'server.py').read_text());policies=[]
  for node in ast.walk(tree):
   if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='send_header' and len(node.args)>=2 and isinstance(node.args[0],ast.Constant) and node.args[0].value=='Content-Security-Policy':policies.append(ast.literal_eval(node.args[1]))
  self.assertEqual(len(policies),1);img_sources=next(p.split()[1:] for p in policies[0].split(';') if p.strip().startswith('img-src '));maps=0
  for path in (ROOT/'static').glob('*.js'):
   if path.name.startswith('leaflet'):continue
   for url in re.findall(r"L\.tileLayer\(['\"]([^'\"]+)",path.read_text()):
    origin=urlsplit(url);self.assertIn(origin.scheme+'://'+origin.netloc,img_sources,path.name+' uses a blocked tile host');maps+=1
  self.assertGreaterEqual(maps,2)
if __name__=='__main__':unittest.main()
