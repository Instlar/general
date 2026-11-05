from pathlib import Path
import json,unittest,re
ROOT=Path(__file__).resolve().parents[1]
R=json.loads((ROOT/'data/recipes.json').read_text())
class BakingTest(unittest.TestCase):
 def test_count_and_unique(self):
  self.assertEqual(len(R),11);self.assertEqual(len(set(x['slug'] for x in R)),len(R))
 def test_pages(self):
  for r in R:
   p=ROOT/'public/recipes'/r['slug']/'index.html';self.assertTrue(p.is_file());txt=p.read_text();self.assertIn('application/ld+json',txt);self.assertIn(r['sourceUrl'],txt)
 def test_ingredients_in_steps(self):
  for r in R:
   ids={x['id'] for x in r['ingredients']};used={y for s in r['steps'] for y in re.findall(r'\{\{([a-z][a-z0-9_]*)(?::0\.5|:0\.25)?\}\}',s)}
   self.assertEqual(ids,used,r['slug'])
 def test_static(self):
  self.assertTrue((ROOT/'public/index.html').exists());self.assertTrue((ROOT/'public/app.js').exists())
  self.assertLess(sum(p.stat().st_size for p in (ROOT/'public/assets').glob('*.webp')),500_000)
