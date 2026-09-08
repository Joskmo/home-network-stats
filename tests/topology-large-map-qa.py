"""Persist the visible positions of large maps, including zoomed dragging."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('base', Path(__file__).with_name('topology-regressions-qa.py'))
assert spec is not None and spec.loader is not None
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)


class LargeMap(base.EditorLifecycle):
    def test_numeric_edit_after_arrange_is_visible_and_survives_drag(self):
        self.button('Auto arrange').click()
        self.page.locator('[data-node="d"]').click()
        self.page.locator('#map-x').fill('510')
        self.page.locator('#map-y').fill('430')
        self.button('Apply to draft').click()
        node = self.page.locator('[data-node="d"]')
        self.assertEqual(node.evaluate('n=>[parseFloat(n.style.left),parseFloat(n.style.top)]'), [510,430])
        node.scroll_into_view_if_needed()
        box = node.bounding_box()
        self.page.mouse.move(box['x']+40,box['y']+30)
        self.page.mouse.down()
        self.page.mouse.move(box['x']+70,box['y']+50,steps=4)
        self.page.mouse.up()
        self.button('Save map').click()
        self.assertEqual(self.page.evaluate("saved.nodes.filter(n=>n.id==='d').map(n=>[n.x,n.y])[0]"), [540,450])
        self.page.evaluate('fixture=structuredClone(saved)')
        self.button('Reload saved map').click()
        self.assertEqual(node.evaluate('n=>[parseFloat(n.style.left),parseFloat(n.style.top)]'), [540,450])

    def test_large_map_position_round_trip(self):
        self.page.evaluate("""() => {
          fixture.nodes.push(...Array.from({length:22},(_,i)=>({id:'n'+i,name:'Client '+i,type:'desktop',ip:'',mac:'',x:80+(i%3)*280,y:1200+Math.floor(i/3)*220})));
        }""")
        self.button('Reload saved map').click()
        node = self.page.locator('[data-node="n0"]')
        self.assertEqual(node.evaluate('n=>parseFloat(n.style.top)'), 1200)
        self.button('Auto arrange').click()
        visible = self.page.locator('.map-node').evaluate_all('(nodes)=>Object.fromEntries(nodes.map(n=>[n.dataset.node,{x:parseFloat(n.style.left),y:parseFloat(n.style.top)}]))')
        self.button('Save map').click()
        saved = self.page.evaluate('saved.nodes')
        self.assertTrue(any(n['y'] > 800 for n in saved))
        for n in saved:
            self.assertEqual({'x':n['x'],'y':n['y']}, visible[n['id']])
        self.page.evaluate('fixture=structuredClone(saved)')
        self.button('Reload saved map').click()
        restored = self.page.locator('.map-node').evaluate_all('(nodes)=>Object.fromEntries(nodes.map(n=>[n.dataset.node,{x:parseFloat(n.style.left),y:parseFloat(n.style.top)}]))')
        self.assertEqual(restored, visible)
        self.button('Zoom out').click()
        node = self.page.locator('[data-node="n21"]')
        node.scroll_into_view_if_needed()
        box = node.bounding_box()
        scale = node.evaluate('n=>n.getBoundingClientRect().width/n.offsetWidth')
        before = node.evaluate('n=>parseFloat(n.style.top)')
        self.page.mouse.move(box['x']+40,box['y']+30)
        self.page.mouse.down()
        self.page.mouse.move(box['x']+40,box['y']+30+40*scale,steps=4)
        self.page.mouse.up()
        self.button('Save map').click()
        self.assertAlmostEqual(self.page.evaluate("saved.nodes.find(n=>n.id==='n21').y"), before+40, delta=1)


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite([
        LargeMap('test_large_map_position_round_trip'),
        LargeMap('test_numeric_edit_after_arrange_is_visible_and_survives_drag'),
    ]))
    raise SystemExit(not result.wasSuccessful())
