"""Security regression tests: no network data before rotation."""
import tempfile
import unittest
from pathlib import Path


class AuthTests(unittest.TestCase):
    def test_bootstrap_cannot_read_data_until_rotation(self):
        from dashboard.auth import Auth
        with tempfile.TemporaryDirectory() as tmp:
            auth = Auth(Path(tmp)/'auth.json', 'test-bootstrap')
            token, session = auth.session()
            self.assertFalse(auth.allowed(session))
            self.assertTrue(auth.login(session, 'test-bootstrap', '127.0.0.1'))
            self.assertFalse(auth.allowed(session))
            with self.assertRaises(ValueError):
                auth.change(session, 'short')
            replacement = auth.change(session, 'a-new-private-password')
            self.assertNotIn(token, auth.sessions)
            self.assertTrue(auth.allowed(auth.sessions[replacement]))
            self.assertNotIn('a-new-private-password', (Path(tmp)/'auth.json').read_text())
            self.assertFalse(Auth(Path(tmp)/'auth.json', None).verify('test-bootstrap'))


class WebTests(unittest.TestCase):
    def test_ipv6_loopback_host_with_port(self):
        from dashboard.web import Application
        from dashboard.auth import Auth
        with tempfile.TemporaryDirectory() as tmp:
            app = Application(Auth(Path(tmp)/'auth.json', 'test-bootstrap'), lambda: {})
            status=[]
            app({'HTTP_HOST':'[::1]:18080','REMOTE_ADDR':'::1','PATH_INFO':'/api/session'}, lambda s,h: status.append(s))
            self.assertEqual(status[0], '200 OK')

    def test_auth_gate_csrf_rotation_logout_and_public_bootstrap_block(self):
        import io, json
        from dashboard.web import Application
        from dashboard.auth import Auth
        with tempfile.TemporaryDirectory() as tmp:
            auth = Auth(Path(tmp)/'auth.json', 'test-bootstrap')
            app = Application(auth, lambda: {'secret_stats': 42})
            cookie = ''
            def request(path='/', method='GET', data=None, host='localhost:18080', origin='http://localhost:18080', forwarded=False):
                nonlocal cookie
                raw = json.dumps(data or {}).encode()
                env = {'PATH_INFO':path, 'REQUEST_METHOD':method, 'HTTP_HOST':host,
                       'REMOTE_ADDR':'127.0.0.1', 'HTTP_ORIGIN':origin, 'HTTP_COOKIE':cookie,
                       'CONTENT_LENGTH':str(len(raw)), 'CONTENT_TYPE':'application/json',
                       'wsgi.input':io.BytesIO(raw)}
                if forwarded: env['HTTP_X_FORWARDED_FOR']='192.168.1.2'
                result = {}
                def start(status, headers):
                    nonlocal cookie
                    result['status']=int(status.split()[0]); result['headers']=dict(headers)
                    if 'Set-Cookie' in result['headers']: cookie=result['headers']['Set-Cookie'].split(';')[0]
                result['body']=b''.join(app(env,start)).decode()
                return result
            self.assertEqual(request('/api/stats')['status'],401)
            first=request('/api/session'); csrf=json.loads(first['body'])['csrf']
            self.assertIn('HttpOnly',first['headers']['Set-Cookie'])
            self.assertIn('Secure',first['headers']['Set-Cookie'])
            self.assertIn('SameSite=Strict',first['headers']['Set-Cookie'])
            self.assertEqual(request('/api/login','POST',{'password':'test-bootstrap'})['status'],403)
            self.assertEqual(request('/api/login','POST',{'password':'test-bootstrap','csrf':csrf},forwarded=True)['status'],403)
            login=request('/api/login','POST',{'password':'test-bootstrap','csrf':csrf})
            self.assertEqual(login['status'],200)
            self.assertNotIn('secret_stats',request()['body'])
            self.assertEqual(request('/api/stats')['status'],403)
            csrf=json.loads(login['body'])['csrf']
            self.assertEqual(request('/api/password','POST',{'password':'long-new-password','csrf':csrf},origin='https://evil.invalid')['status'],403)
            rotated=request('/api/password','POST',{'password':'long-new-password','csrf':csrf})
            self.assertEqual(rotated['status'],200)
            self.assertEqual(json.loads(request('/api/stats')['body']),{'secret_stats':42})
            self.assertEqual(request('/api/stats',host='home-lan.jos-dev.ru')['status'],403)
            csrf=json.loads(rotated['body'])['csrf']
            self.assertEqual(request('/api/logout','POST',{'csrf':csrf})['status'],200)
            self.assertEqual(request('/api/stats')['status'],401)
            for _ in range(4): request('/api/login','POST',{'password':'wrong','csrf':json.loads(request('/api/session')['body'])['csrf']})
            self.assertEqual(request('/api/login','POST',{'password':'wrong','csrf':json.loads(request('/api/session')['body'])['csrf']})['status'],429)


class DataTests(unittest.TestCase):
    def test_month_is_read_only_partial_and_never_backfills(self):
        import json, sqlite3
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from dashboard.data import monthly
        now = datetime(2026,9,7,12,tzinfo=ZoneInfo('Europe/Moscow')).timestamp()
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'history.sqlite'
            db=sqlite3.connect(path)
            db.executescript('CREATE TABLE intervals(start REAL,end REAL,usage TEXT,covered REAL,issues TEXT); CREATE TABLE meta(key TEXT,value TEXT);')
            db.execute('INSERT INTO intervals VALUES(?,?,?,?,?)',(now-300,now,json.dumps({'device-a':500,'device-b':250}),300,'[]'))
            db.commit(); db.close()
            before=path.read_bytes()
            report=monthly(path,now)
            self.assertEqual(report['total_bytes'],750)
            self.assertTrue(report['partial'])
            self.assertEqual(report['collection_started'],now-300)
            self.assertEqual(report['covered_seconds'],300)
            self.assertEqual(path.read_bytes(),before)
            self.assertFalse((Path(tmp)/'missing').exists())
            self.assertFalse(monthly(Path(tmp)/'missing',now)['available'])

    def test_wan_monthly_persists_only_measured_counter_deltas(self):
        from dashboard.sampler import record_wan
        from dashboard.data import monthly
        import time
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'wan.sqlite3'; now=time.time()
            a={'device':'wan','rx_bytes':1000,'tx_bytes':500,'uptime':20}
            b={'device':'wan','rx_bytes':3000,'tx_bytes':1000,'uptime':25}
            record_wan(path,None,a,now-5,now-5,0)
            record_wan(path,a,b,now-5,now,5)
            record_wan(path,b,a,now,now+5,5)
            report=monthly(path,now+5)
            self.assertEqual(report['total_bytes'],2500)
            self.assertEqual(report['covered_seconds'],5)
            self.assertTrue(report['partial'])

    def test_speed_delta_reset_gap_and_stale_sample(self):
        from dashboard.sampler import speed_delta
        from dashboard.data import speed
        import json, time
        a={'device':'wan','rx_bytes':1000,'tx_bytes':500,'uptime':20}
        b={'device':'wan','rx_bytes':3000,'tx_bytes':1000,'uptime':25}
        self.assertEqual(speed_delta(a,b,5)['download_bps'],3200)
        self.assertEqual(speed_delta(a,b,5)['upload_bps'],800)
        self.assertIsNone(speed_delta(a,a|{'uptime':1},5))
        self.assertIsNone(speed_delta(a,b,100))
        self.assertIsNone(speed_delta(b,a,5))
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'speed.json'
            path.write_text(json.dumps({'sampled_at':time.time()-60,'download_bps':100,'upload_bps':200}))
            self.assertIsNone(speed(path)['download_bps'])
            self.assertTrue(speed(path)['stale'])


class ConfigTests(unittest.TestCase):
    def test_bootstrap_file_permissions_and_default_private_bind(self):
        from dashboard.__main__ import build_app
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'bootstrap'; path.write_text('test-bootstrap'); path.chmod(0o644)
            env={'DASHBOARD_AUTH_FILE':str(Path(tmp)/'auth/state.json'),'DASHBOARD_BOOTSTRAP_FILE':str(path),'DASHBOARD_HISTORY_FILE':str(Path(tmp)/'history'),'DASHBOARD_SPEED_FILE':str(Path(tmp)/'speed')}
            with self.assertRaises(ValueError): build_app(env)
            path.chmod(0o600)
            app=build_app(env)
            self.assertFalse(app.public_enabled)
            self.assertTrue(app.auth.state['must_change'])


class LanProxyTests(unittest.TestCase):
    def test_lan_bootstrap_requires_exact_proxy_and_last_forwarded_hop(self):
        from dashboard.web import private_lan_request
        env={'REMOTE_ADDR':'172.20.0.2','HTTP_HOST':'home-lan.jos-dev.ru','HTTP_X_FORWARDED_FOR':'192.168.1.80','HTTP_X_FORWARDED_PROTO':'https'}
        self.assertTrue(private_lan_request(env,'172.20.0.2','192.168.1.0/24','home-lan.jos-dev.ru'))
        self.assertFalse(private_lan_request(env|{'REMOTE_ADDR':'172.20.0.3'},'172.20.0.2','192.168.1.0/24','home-lan.jos-dev.ru'))
        self.assertFalse(private_lan_request(env|{'HTTP_X_FORWARDED_FOR':'192.168.1.80, 8.8.8.8'},'172.20.0.2','192.168.1.0/24','home-lan.jos-dev.ru'))
        self.assertFalse(private_lan_request(env|{'HTTP_X_FORWARDED_PROTO':'http'},'172.20.0.2','192.168.1.0/24','home-lan.jos-dev.ru'))
        self.assertFalse(private_lan_request(env,'','192.168.1.0/24','home-lan.jos-dev.ru'))


if __name__ == '__main__': unittest.main()
