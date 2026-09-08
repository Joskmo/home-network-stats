"""Headless browser QA of the real bundle using an isolated bridge fixture.

No live API/device data. Run after npm run build with:
uv run --with playwright python tests/topology-editor-v2-qa.py
Native CDP wheel tests are Chromium event tests, not physical Mac gestures.
"""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('regressions', Path(__file__).with_name('topology-regressions-qa.py'))
assert spec is not None and spec.loader is not None
regressions = importlib.util.module_from_spec(spec)
spec.loader.exec_module(regressions)


class DirectEditor(regressions.EditorLifecycle):
    def wire_point(self):
        self.page.locator('.map-scroll').scroll_into_view_if_needed()
        return self.page.locator('.map-wire').first.evaluate("""p=>{
          const m=p.getScreenCTM();
          for(let t=0.15;t<0.9;t+=0.03){const a=p.getPointAtLength(p.getTotalLength()*t),q=new DOMPoint(a.x,a.y).matrixTransform(m);
            if(document.elementFromPoint(q.x,q.y)?.matches('.map-wire-hit'))return {x:q.x,y:q.y};}
          return null;
        }""")

    def test_direct_wire_drag_save_reload(self):
        point = self.wire_point()
        self.assertIsNotNone(point, 'visible wire must have an interactive stroke hit target')
        self.page.mouse.click(**point)
        handles = self.page.locator('.map-route-handle')
        self.assertGreater(handles.count(), 0, 'single wire click must expose bends immediately')
        handle = handles.first
        handle.scroll_into_view_if_needed()
        box = handle.bounding_box()
        x,y = box['x']+box['width']/2,box['y']+box['height']/2
        self.page.mouse.move(x,y)
        self.page.mouse.down()
        self.page.mouse.move(x+40,y+25,steps=5)
        paths = self.page.evaluate("""()=>{const v=document.querySelector('.map-wire.is-active');return [...document.querySelectorAll('[data-route]')].filter(p=>p.dataset.route===v.dataset.route&&p.tagName==='path').map(p=>p.getAttribute('d'))}""")
        self.assertEqual(len(paths), 2)
        self.assertEqual(paths[0],paths[1], 'visual and hit paths must preview together')
        self.page.mouse.up()
        self.button('Save map').click()
        self.assertGreater(self.page.evaluate('Object.values(saved.routes)[0].length'),0)
        visible = self.page.locator('.map-wire').first.get_attribute('d')
        self.page.evaluate('fixture=structuredClone(saved)')
        self.button('Reload saved map').click()
        self.assertEqual(self.page.locator('.map-wire').first.get_attribute('d'), visible)
        self.assertGreater(handles.count(),0, 'selected wire survives graph replacement')

    def test_scoped_cursor_zoom_and_pan(self):
        page = self.page
        page.locator('.map-scroll').scroll_into_view_if_needed()
        page.evaluate("""()=>{const c=document.querySelector('.map-canvas');
          c.style.width='2000px';c.style.height='1800px';
          const s=document.querySelector('.map-scroll');s.scrollBy(200,180)}""")
        box = page.locator('.map-scroll').bounding_box()
        x, y = box['x'] + 180, box['y'] + 160
        world = """([x,y])=>{const c=document.querySelector('.map-canvas'),r=c.getBoundingClientRect(),z=r.width/c.offsetWidth;
          return {x:(x-r.x)/z,y:(y-r.y)/z,z}}"""
        before = page.evaluate(world, [x,y])
        cdp = page.context.new_cdp_session(page)
        cdp.send('Input.dispatchMouseEvent', {'type':'mouseWheel','x':x,'y':y,'deltaX':0,'deltaY':-100,'modifiers':2})
        page.wait_for_timeout(100)
        after = page.evaluate(world, [x,y])
        self.assertGreater(after['z'], before['z'], 'ctrl+wheel must zoom the map')
        self.assertAlmostEqual(after['x'], before['x'], delta=2)
        self.assertAlmostEqual(after['y'], before['y'], delta=2)
        start = page.locator('.map-scroll').evaluate('s=>[s.scrollLeft,s.scrollTop]')
        page.mouse.move(x,y)
        page.mouse.wheel(90,80)
        page.wait_for_timeout(150)
        end = page.locator('.map-scroll').evaluate('s=>[s.scrollLeft,s.scrollTop]')
        self.assertGreater(end[0], start[0])
        self.assertGreater(end[1], start[1])
        self.assertEqual(page.evaluate("getComputedStyle(document.querySelector('.map-scroll')).overscrollBehavior"), 'contain')
        self.assertFalse(page.evaluate("""()=>{const e=new WheelEvent('wheel',{ctrlKey:true,deltaY:40,bubbles:true,cancelable:true});document.body.dispatchEvent(e);return e.defaultPrevented}"""))

    def test_wire_menu_add_remove_and_bound(self):
        point = self.wire_point()
        self.page.mouse.click(**point, button='right')
        menu = self.page.locator('.map-context-menu')
        self.assertEqual(menu.count(), 1, 'wire context menu must open')
        self.assertIn('Edit physical cable', menu.inner_text())
        self.assertNotIn('Delete', menu.inner_text())
        menu.get_by_role('menuitem', name='Add bend', exact=True).click()
        self.button('Save map').click()
        initial = self.page.evaluate('Object.values(saved.routes)[0].length')
        for _ in range(10):
            point = self.wire_point()
            self.page.mouse.click(**point, button='right')
            add = menu.get_by_role('menuitem', name='Add bend', exact=True)
            if add.is_disabled():
                self.page.keyboard.press('Escape')
                break
            add.click()
        self.button('Save map').click()
        self.assertEqual(self.page.evaluate('Object.values(saved.routes)[0].length'), 8)
        self.assertLess(initial, 8)
        handle = self.page.locator('.map-route-handle').first
        handle.focus()
        self.page.keyboard.press('Delete')
        self.button('Save map').click()
        self.assertEqual(self.page.evaluate('Object.values(saved.routes)[0].length'), 7)
        point = self.wire_point()
        self.page.mouse.click(**point,button='right')
        self.page.mouse.click(5,5)
        self.assertEqual(menu.count(),0)
        self.assertFalse(self.page.evaluate("""()=>{const e=new MouseEvent('contextmenu',{bubbles:true,cancelable:true});document.body.dispatchEvent(e);return e.defaultPrevented}"""))

    def test_compact_stable_inspector_mobile(self):
        scroll = self.page.locator('.map-scroll')
        panel = self.page.locator('#map-inspector')
        self.assertLess(panel.bounding_box()['width'], 310, 'desktop inspector is a narrow side pane')
        self.assertGreater(panel.bounding_box()['x'], scroll.bounding_box()['x'])
        before = scroll.bounding_box()
        self.page.locator('[data-node="r"]').hover()
        self.assertEqual(scroll.bounding_box(), before)
        artifacts = Path(__file__).resolve().parents[1] / 'output/playwright'
        artifacts.mkdir(parents=True,exist_ok=True)
        self.page.locator('.map-workspace').screenshot(path=str(artifacts/'editor-v2-desktop.png'))
        self.page.set_viewport_size({'width':390,'height':844})
        self.page.mouse.move(0,0)
        self.page.wait_for_timeout(250)
        self.assertLess(panel.bounding_box()['height'], 180, 'mobile details are compact, below the map')
        self.assertGreaterEqual(panel.bounding_box()['y'],scroll.bounding_box()['y']+scroll.bounding_box()['height'])
        self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'),390)
        self.page.locator('.map-workspace').screenshot(path=str(artifacts/'editor-v2-mobile.png'))

    def test_poll_does_not_interrupt_captured_route(self):
        self.page.mouse.click(**self.wire_point())
        h = self.page.locator('.map-route-handle').first
        h.scroll_into_view_if_needed()
        box = h.bounding_box()
        x,y = box['x']+9,box['y']+9
        self.page.mouse.move(x,y)
        self.page.mouse.down()
        self.page.mouse.move(x+35,y+20,steps=4)
        self.page.evaluate('window.captured=document.querySelector(".map-route-handle");window.beforeCalls=calls.length;pollTopology()')
        self.page.wait_for_timeout(30)
        self.assertTrue(self.page.evaluate('captured===document.querySelector(".map-route-handle")'), 'background poll must not replace captured handle')
        self.assertEqual(self.page.evaluate('calls.length'),self.page.evaluate('beforeCalls'))
        self.page.mouse.move(x+45,y+30)
        self.page.mouse.up()
        self.assertTrue(self.button('Save map').is_enabled())

    def test_hover_details_survive_normal_pointer_travel(self):
        self.page.locator('[data-node="d"]').hover()
        scope = self.page.locator('.map-scroll').bounding_box()
        self.page.mouse.move(scope['x']+scope['width']-8,scope['y']+30)
        self.page.wait_for_timeout(600)
        self.assertIn('Desktop',self.page.locator('#map-inspector').inner_text())
        self.button('Adjust route').click()
        self.assertGreater(self.page.locator('.map-route-handle').count(),0)

    def test_fit_zoom_out_anchor_and_four_way_pan(self):
        self.button('Fit map').click()
        self.page.locator('.map-scroll').scroll_into_view_if_needed()
        box = self.page.locator('.map-scroll').bounding_box()
        canvas = self.page.locator('.map-canvas').bounding_box()
        self.assertAlmostEqual(canvas['x']+canvas['width']/2,box['x']+box['width']/2,delta=2)
        self.assertAlmostEqual(canvas['y']+canvas['height']/2,box['y']+box['height']/2,delta=2)
        x,y = box['x']+200,box['y']+150
        world = """([x,y])=>{const c=document.querySelector('.map-canvas'),r=c.getBoundingClientRect(),z=r.width/c.offsetWidth;return [(x-r.x)/z,(y-r.y)/z]}"""
        before = self.page.evaluate(world,[x,y])
        cdp = self.page.context.new_cdp_session(self.page)
        cdp.send('Input.dispatchMouseEvent',{'type':'mouseWheel','x':x,'y':y,'deltaX':0,'deltaY':60,'modifiers':2})
        self.page.wait_for_timeout(100)
        after = self.page.evaluate(world,[x,y])
        for a,b in zip(before,after): self.assertAlmostEqual(a,b,delta=2)
        self.page.mouse.move(x,y)
        for dx,dy in [(-80,0),(0,-80),(80,0),(0,80)]:
            before = self.page.locator('.map-canvas').bounding_box()
            self.page.mouse.wheel(dx,dy)
            self.page.wait_for_timeout(150)
            after = self.page.locator('.map-canvas').bounding_box()
            self.assertAlmostEqual(after['x']-before['x'],-dx,delta=2)
            self.assertAlmostEqual(after['y']-before['y'],-dy,delta=2)

    def test_stale_handle_cannot_mutate_replaced_graph(self):
        self.page.mouse.click(**self.wire_point())
        self.page.evaluate('window.staleHandle=document.querySelector(".map-route-handle")')
        self.button('Reload saved map').click()
        self.page.evaluate("staleHandle.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true,cancelable:true}))")
        self.assertTrue(self.button('Save map').is_disabled(), 'detached old-render handlers cannot change the new graph')

    def test_pan_gestures_and_keyboard_scoped_menu(self):
        self.button('Fit map').click()
        scope = self.page.locator('.map-scroll')
        scope.scroll_into_view_if_needed()
        rect = scope.bounding_box()
        x,y = rect['x']+80,rect['y']+70
        for middle in [False,True]:
            scope.focus()
            if not middle: self.page.keyboard.down('Space')
            before = scope.evaluate('s=>[s.scrollLeft,s.scrollTop]')
            self.page.mouse.move(x,y)
            self.page.mouse.down(button='middle' if middle else 'left')
            self.page.mouse.move(x+50,y+40,steps=4)
            self.page.mouse.up(button='middle' if middle else 'left')
            if not middle: self.page.keyboard.up('Space')
            after = scope.evaluate('s=>[s.scrollLeft,s.scrollTop]')
            self.assertAlmostEqual(after[0]-before[0],-50,delta=1)
            self.assertAlmostEqual(after[1]-before[1],-40,delta=1)
            self.assertTrue(self.page.locator('#map-form').is_hidden())
        self.page.mouse.click(rect['x']+rect['width']-20, min(980,rect['y']+rect['height']-20),button='right')
        menu = self.page.locator('.map-context-menu')
        menu_box = menu.bounding_box()
        self.assertGreaterEqual(menu_box['x'],rect['x'])
        self.assertLessEqual(menu_box['x']+menu_box['width'],rect['x']+rect['width']+1)
        self.assertLessEqual(menu_box['y']+menu_box['height'],min(1000,rect['y']+rect['height'])+1)
        self.page.keyboard.press('Escape')
        self.assertEqual(menu.count(),0)
        scope.focus()
        self.page.keyboard.press('Shift+F10')
        self.assertEqual(menu.count(),1)
        self.page.keyboard.press('ArrowDown')
        self.assertEqual(self.page.evaluate('document.activeElement.textContent'),'Auto arrange')
        self.page.keyboard.press('Escape')
        self.assertTrue(scope.evaluate('s=>s===document.activeElement'))

    def test_double_click_bend_and_unscaled_handle(self):
        point = self.wire_point()
        self.page.mouse.dblclick(**point)
        self.assertTrue(self.button('Save map').is_enabled())
        handles = self.page.locator('.map-route-handle')
        before = handles.first.bounding_box()['width']
        self.button('Zoom out').click()
        self.button('Zoom out').click()
        self.assertAlmostEqual(handles.first.bounding_box()['width'],before,delta=0.5,
                               msg='route handles remain usable at every map zoom')
        # Nearby bends may overlap at low zoom; hit the visible topmost handle.
        box = handles.first.bounding_box()
        self.page.mouse.click(box['x']+box['width']/2,box['y']+box['height']/2,button='right')
        self.page.get_by_role('menuitem',name='Remove bend',exact=True).click()
        self.button('Save map').click()
        zoom = self.page.locator('.map-canvas').evaluate('c=>c.style.zoom')
        self.page.evaluate('pollTopology()')
        self.assertEqual(self.page.locator('.map-canvas').evaluate('c=>c.style.zoom'),zoom)


if __name__ == '__main__':
    suite = unittest.TestSuite(DirectEditor(name) for name in DirectEditor.__dict__ if name.startswith('test_'))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(not result.wasSuccessful())