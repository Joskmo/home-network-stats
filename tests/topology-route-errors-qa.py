"""Focused isolated route/editor and actionable save-error regressions."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('regressions', Path(__file__).with_name('topology-regressions-qa.py'))
assert spec is not None
regressions = importlib.util.module_from_spec(spec)
assert spec is not None and spec.loader is not None
spec.loader.exec_module(regressions)


class RouteErrors(regressions.EditorLifecycle):

    def test_actionable_save_errors_preserve_draft_and_language(self):
        for lang, session_text, csrf_text in [('en', 'Sign in', 'security token'), ('ru', 'Войдите', 'токен')]:
            self.page.evaluate('(lang)=>{dashboardBridge.language=lang;document.documentElement.lang=lang}', lang)
            self.page.wait_for_timeout(30)
            self.page.locator('.map-tools button').nth(3).click()  # Arrange draft.
            for code, status, text in [('login_required', 401, session_text), ('csrf_failed', 403, csrf_text)]:
                self.page.evaluate('(error)=>window.rejection=error', {'code': code, 'status': status})
                # The captured API dispatches through calls.push before storing a save.
                self.page.evaluate('''()=>{if(!window.pushCalls){window.pushCalls=calls.push;calls.push=function(call){
                  if(call.write && rejection) throw Object.assign(new Error('rejected'),rejection);
                  return pushCalls.call(this,call);
                }}}''')
                self.page.locator('#map-save').click()
                self.assertIn(text, self.page.locator('#map-message').inner_text())
                self.assertTrue(self.page.locator('#map-save').is_enabled())
                self.assertEqual(self.page.locator('.map-node').count(), 2)
                self.page.evaluate('window.rejection=null')
                self.page.locator('#map-save').click()
                self.page.wait_for_function('!!window.saved')
                self.assertEqual(self.page.evaluate('saved.nodes.length'), 2)
                self.page.locator('.map-tools button').nth(3).click()

    def test_busy_transition_cancels_active_route_preview(self):
        self.page.locator('[data-node="d"]').hover()
        self.button('Adjust route').click()
        before = self.page.locator('.map-wire.is-active').get_attribute('d')
        self.page.locator('.map-route-handle').first.evaluate('''h=>{
          h.setPointerCapture=()=>{};
          h.dispatchEvent(new PointerEvent('pointerdown',{button:0,pointerId:1,clientX:10,clientY:10}));
          h.dispatchEvent(new PointerEvent('pointermove',{pointerId:1,clientX:60,clientY:40}));
        }''')
        self.assertNotEqual(self.page.locator('.map-wire.is-active').get_attribute('d'), before)
        self.button('Refresh discovered devices').evaluate('b=>b.click()')
        self.assertEqual(self.page.locator('.map-wire.is-active').get_attribute('d'), before)
        self.assertTrue(self.page.locator('.map-route-handle').first.is_enabled())
        self.page.locator('.map-route-handle').first.dispatch_event('pointerup', {'pointerId': 1})
        self.assertTrue(self.page.locator('#map-save').is_disabled())

    def test_node_apply_restores_route_controls_and_save_reason(self):
        self.page.locator('[data-node="d"]').hover()
        self.button('Adjust route').click()
        self.page.locator('[data-node="r"]').click()
        self.assertIn('finish', self.page.locator('#map-save').get_attribute('title', timeout=1000) or '')
        self.page.locator('#map-name').fill('Changed router')
        self.page.locator('#map-form').get_by_role('button', name='Apply to draft', exact=True).click()
        self.assertTrue(self.page.locator('.map-route-handle').first.is_enabled())
        self.assertEqual(self.page.locator('#map-save').get_attribute('title'), '')
        self.button('Reset route to automatic').click()
        self.assertEqual(self.page.locator('.map-route-handle').count(), 0)
        self.button('Save map').click()
        self.assertEqual(self.page.evaluate("saved.nodes.find(n=>n.id==='r').name"), 'Changed router')


if __name__ == '__main__':
    suite = unittest.TestSuite(RouteErrors(name) for name in (
        'test_actionable_save_errors_preserve_draft_and_language',
        'test_busy_transition_cancels_active_route_preview',
        'test_node_apply_restores_route_controls_and_save_reason',
    ))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(not result.wasSuccessful())
