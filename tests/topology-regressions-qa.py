"""Headless, isolated regressions. Run after npm run build:
uv run --with playwright python tests/topology-regressions-qa.py
No live server: every request is fulfilled locally.
"""
from pathlib import Path
import unittest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


class EditorLifecycle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.page = self.browser.new_page(viewport={"width": 1440, "height": 1000})
        self.errors = []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.page.on("dialog", lambda dialog: dialog.accept())
        self.page.route("**/*", lambda route: route.fulfill(
            content_type="text/html", body='<html lang="en"><main id="dashboard"><section id="topology"></section></main></html>'))
        self.page.goto("http://localhost/qa")
        for file in ("style.css", "topology.css"):
            self.page.add_style_tag(path=str(ROOT / "dashboard/static" / file))
        self.page.evaluate("""() => {
          window.fixture={revision:1,nodes:[
            {id:'r',name:'Router',type:'router',ip:'',mac:'',x:40,y:40,ports:['LAN 1']},
            {id:'d',name:'Desktop',type:'desktop',ip:'',mac:'',x:400,y:300,ports:['eth0']}
          ],links:[{id:'c',source:'r',target:'d',source_port:'LAN 1',target_port:'eth0'}]};
          window.calls=[];
          // Expose only the scheduled topology poll in this isolated fixture.
          const nativeInterval=window.setInterval.bind(window);
          window.setInterval=(fn,ms)=>{if(ms===15000)window.pollTopology=fn;return nativeInterval(fn,ms)};
          window.dashboardBridge={version:1,session:{authenticated:true},language:'en',translate:k=>k,
            replaceSession(s){this.session=s},api:async(url,body)=>{
              calls.push({url,write:!!body});
              if(url.endsWith('/preview'))return structuredClone(body.topology);
              if(body){window.saved=structuredClone(body.topology);return structuredClone(saved);}
              return structuredClone(fixture);
            }};
        }""")
        self.page.add_script_tag(path=str(ROOT / "dashboard/static/topology.js"))
        self.page.wait_for_selector(".map-node")
        self.page.locator(".map-inventory > summary").click()

    def tearDown(self):
        self.page.close()
        self.assertEqual(self.errors, [])

    def button(self, name):
        return self.page.get_by_role("button", name=name, exact=True)

    def check_replacement(self, action):
        self.button("Auto arrange").click()
        self.page.locator('[data-node="r"]').click()
        self.page.locator("#map-name").fill("Edited router")
        target = self.button(action)
        disabled = target.is_disabled()
        before = self.page.evaluate("calls.length")
        # Native click attempts on disabled buttons do nothing; on the old code
        # this exercises the actual graph replacement, not a mocked controller.
        target.evaluate("button => button.click()")
        self.page.locator("#map-form").get_by_role("button", name="Apply to draft", exact=True).click()
        self.button("Save map").click()
        self.page.wait_for_function("window.saved !== undefined")
        self.assertEqual(self.page.evaluate("saved.nodes.find(n=>n.id==='r').name"), "Edited router",
                         f"{action} detached or discarded the editor draft")
        self.assertTrue(disabled, f"{action} must visibly disable while editing")
        self.assertEqual(self.page.evaluate("calls.length"), before + 1)
        self.assertEqual(self.page.evaluate("saved.nodes.length"), 2)
        self.assertTrue(self.button("Reload saved map").is_enabled())
        self.assertTrue(self.button("Insert switch").is_enabled())

    def test_drag_does_not_open_editor_but_click_does(self):
        node = self.page.locator('[data-node="r"]')
        node.scroll_into_view_if_needed()
        box = node.bounding_box()
        x, y = box["x"] + 50, box["y"] + 35
        self.page.mouse.move(x, y)
        self.page.mouse.down()
        self.page.mouse.move(x + 70, y + 45, steps=8)
        self.page.mouse.up()
        self.page.wait_for_timeout(50)  # controller's deferred drag cleanup
        self.assertTrue(self.page.locator("#map-form").is_hidden(),
                        "drag's synthesized click must not open the editor")
        self.assertEqual(node.evaluate("n => n.style.left"), "110px")
        self.assertEqual(node.evaluate("n => n.style.top"), "85px")
        node.click()
        self.assertTrue(self.page.locator("#map-form").is_visible())
        self.assertEqual(self.page.locator("#map-name").input_value(), "Router")
        self.button("Cancel").click()
        node.focus()
        self.page.keyboard.press("Enter")
        self.assertTrue(self.page.locator("#map-form").is_visible())

    def test_repeated_drag_and_save_preserves_latest_position(self):
        node = self.page.locator('[data-node="r"]')
        for left, top in ((110, 85), (180, 130)):
            node.scroll_into_view_if_needed()
            box = node.bounding_box()
            x, y = box["x"] + 50, box["y"] + 35
            self.page.mouse.move(x, y)
            self.page.mouse.down()
            self.page.mouse.move(x + 70, y + 45, steps=8)
            self.page.mouse.up()
            self.page.wait_for_timeout(50)
            self.button("Save map").click()
            self.page.wait_for_function("document.getElementById('map-save').disabled")
            self.assertEqual(self.page.evaluate("saved.nodes.find(n=>n.id==='r').x"), left)
            self.assertEqual(self.page.evaluate("saved.nodes.find(n=>n.id==='r').y"), top)
            self.assertEqual(node.evaluate("n=>parseInt(n.style.left)"), left)
            self.assertTrue(self.page.locator("#map-form").is_hidden())

    def test_preview_apply_waits_for_editor_cancel(self):
        self.button("Refresh discovered devices").click()
        preview_apply = self.page.locator("#map-preview").get_by_role(
            "button", name="Apply to draft", exact=True)
        preview_apply.wait_for()
        self.page.locator('[data-node="r"]').click()
        self.assertTrue(preview_apply.is_disabled())
        self.assertTrue(self.button("Refresh discovered devices").is_disabled())
        self.page.locator("#map-form").get_by_role("button", name="Cancel", exact=True).click()
        self.assertTrue(preview_apply.is_enabled())
        self.assertTrue(self.button("Refresh discovered devices").is_enabled())
        self.assertTrue(self.button("Save map").is_disabled())
        preview_apply.click()
        self.assertTrue(self.button("Save map").is_enabled())

    def test_cable_edit_blocks_split_and_reload(self):
        self.page.locator("#map-lists .map-row").filter(has_text="↔").get_by_role(
            "button", name="Edit", exact=True).click()
        self.page.locator("#map-source_port").fill("LAN 2")
        for action in ("Insert switch", "Reload saved map", "Save map"):
            target = self.button(action)
            self.assertTrue(target.is_disabled(), action)
            target.evaluate("b => b.click()")
        self.page.locator("#map-form").get_by_role("button", name="Apply to draft", exact=True).click()
        self.button("Save map").click()
        self.page.wait_for_function("window.saved !== undefined")
        self.assertEqual(self.page.evaluate("saved.links[0].source_port"), "LAN 2")
        self.assertEqual(self.page.evaluate("saved.links.length"), 1)

    def test_save_during_node_edit(self):
        self.check_replacement("Save map")

    def test_split_during_node_edit(self):
        self.check_replacement("Insert switch")

    def test_reload_during_node_edit(self):
        self.check_replacement("Reload saved map")


if __name__ == "__main__":
    unittest.main(verbosity=2)
