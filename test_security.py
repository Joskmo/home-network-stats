"""All security fixtures are synthetic and isolated from production state."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from dashboard.auth import Auth


class IdentityTests(unittest.TestCase):
    def test_only_fresh_unambiguous_inventory_from_exact_ingress_is_trusted(self):
        import dashboard.access as access
        with tempfile.TemporaryDirectory() as tmp, patch('dashboard.access.time.time', return_value=1000):
            path = Path(tmp)
            device = {'ip':'192.168.1.80','mac':'02:00:00:00:00:80','name':'Fixture phone',
                      'observed_at':1000,'state':'REACHABLE','interface':'br-lan'}
            inventory = {'sampled_at':1000,'source':'router-native','devices':[device]}
            (path/'inventory.json').write_text(json.dumps(inventory))
            (path/'trusted.json').write_text(json.dumps({'macs':[device['mac']]}))
            (path/'trusted.json').chmod(0o600)
            store = access.TrustedDevices(path/'trusted.json', path/'inventory.json')
            env = {'REMOTE_ADDR':'172.22.0.2','HTTP_HOST':'home-lan.jos-dev.ru',
                   'HTTP_X_FORWARDED_PROTO':'https','HTTP_X_FORWARDED_FOR':'192.168.1.80'}
            self.assertEqual(store.identity(env)['mac'],device['mac'])
            for extra in [{'REMOTE_ADDR':'172.22.0.3'}, {'REMOTE_ADDR':'192.168.1.80'},
                          {'HTTP_X_FORWARDED_FOR':'192.168.1.80, 8.8.8.8'},
                          {'HTTP_X_FORWARDED_FOR':'192.168.1.80, 172.22.0.3'},
                          {'HTTP_X_FORWARDED_FOR':'192.168.1.81'},
                          {'HTTP_X_FORWARDED_PROTO':'http'}, {'HTTP_HOST':'evil.invalid'}]:
                self.assertIsNone(store.identity(env|extra))
            for invalid in [inventory|{'sampled_at':950}, inventory|{'source':'http'},
                            inventory|{'devices':[device,device|{'mac':'02:00:00:00:00:81'}]},
                            inventory|{'devices':[device|{'observed_at':950}]},
                            inventory|{'devices':[device|{'state':'STALE'}]}]:
                (path/'inventory.json').write_text(json.dumps(invalid))
                self.assertIsNone(store.identity(env))
            (path/'inventory.json').unlink()
            self.assertIsNone(store.identity(env))


class ManagementTests(unittest.TestCase):
    def test_only_admin_or_fresh_trusted_device_manages_and_recovers(self):
        from dashboard.access import TrustedDevices, AccessDenied
        with tempfile.TemporaryDirectory() as tmp, patch('dashboard.access.time.time', return_value=1000):
            path=Path(tmp)
            row={'ip':'192.168.1.80','mac':'02:00:00:00:00:80','name':'Fixture phone',
                 'observed_at':1000,'state':'REACHABLE','interface':'br-lan'}
            (path/'inventory.json').write_text(json.dumps({'sampled_at':1000,'source':'router-native','devices':[row]}))
            store=TrustedDevices(path/'trusted.json',path/'inventory.json')
            auth=Auth(path/'auth.json','fixture-password')
            _, anon=auth.session()
            env={'REMOTE_ADDR':'172.22.0.2','HTTP_HOST':'home-lan.jos-dev.ru',
                 'HTTP_X_FORWARDED_PROTO':'https','HTTP_X_FORWARDED_FOR':row['ip']}
            with self.assertRaises(AccessDenied): store.update(auth,anon,env,'add',row['mac'])
            with self.assertRaises(AccessDenied): store.recover(auth,anon,env,'replacement-password')
            self.assertTrue(auth.verify('fixture-password'))
            auth.login(anon,'fixture-password','ignored')
            admin_token=auth.change(anon,'rotated-fixture-password')
            admin=auth.sessions[admin_token]
            with self.assertRaises(ValueError): store.update(auth,admin,{},'add','02:00:00:00:00:99')
            store.update(auth,admin,{},'add',row['mac'])
            self.assertEqual(TrustedDevices(path/'trusted.json',path/'inventory.json').identity(env)['mac'],row['mac'])
            _, fresh=auth.session()
            with self.assertRaises(AccessDenied): store.recover(auth,admin,{},'replacement-password')
            token=store.recover(auth,fresh,env,'replacement-password')
            self.assertTrue(auth.verify('replacement-password'))
            self.assertFalse(auth.verify('rotated-fixture-password'))
            self.assertEqual(list(auth.sessions),[token])
            with self.assertRaises(AccessDenied): store.update(auth,admin,{},'remove',row['mac'])
            with patch('dashboard.access.time.time',return_value=1011):
                store.update(auth,auth.sessions[token],env,'remove',row['mac'])
            self.assertIsNone(store.identity(env))


class MutationLimitTests(unittest.TestCase):
    def test_mutations_are_persistently_rate_limited(self):
        from dashboard.access import TrustedDevices
        from dashboard.auth import RateLimited
        with tempfile.TemporaryDirectory() as tmp, patch('dashboard.access.time.time',return_value=1000):
            p=Path(tmp)
            row={'ip':'192.168.1.80','mac':'02:00:00:00:00:80','name':'Fixture',
                 'observed_at':1000,'state':'REACHABLE','interface':'br-lan'}
            (p/'inventory').write_text(json.dumps({'sampled_at':1000,'source':'router-native','devices':[row]}))
            auth=Auth(p/'auth','fixture-password')
            _,s=auth.session(); auth.login(s,'fixture-password','ignored')
            token=auth.change(s,'rotated-fixture-password'); s=auth.sessions[token]
            store=TrustedDevices(p/'trusted',p/'inventory')
            store.update(auth,s,{},'add',row['mac'])
            store=TrustedDevices(p/'trusted',p/'inventory')
            with self.assertRaises(RateLimited) as caught: store.update(auth,s,{},'remove',row['mac'])
            self.assertEqual(caught.exception.retry_after,10)


class SecureWebTests(unittest.TestCase):
    def test_trust_is_request_scoped_csrf_recovery_and_retry_header(self):
        import io
        from dashboard.access import TrustedDevices
        from dashboard.web import Application
        with tempfile.TemporaryDirectory() as tmp, patch('dashboard.access.time.time',return_value=1000):
            p=Path(tmp)
            row={'ip':'192.168.1.80','mac':'02:00:00:00:00:80','name':'Fixture',
                 'observed_at':1000,'state':'REACHABLE','interface':'br-lan'}
            (p/'inventory').write_text(json.dumps({'sampled_at':1000,'source':'router-native','devices':[row]}))
            (p/'trusted').write_text(json.dumps({'macs':[row['mac']]})); (p/'trusted').chmod(0o600)
            auth=Auth(p/'auth','fixture-password')
            _,s=auth.session(); auth.login(s,'fixture-password','ignored'); auth.change(s,'rotated-fixture-password')
            app=Application(auth,lambda:{'private':42},trusted_lan_proxy='172.22.0.2',
                            public_enabled=True,access=TrustedDevices(p/'trusted',p/'inventory'))
            cookie=''
            def req(path='/api/session', data=None, xff='192.168.1.80',origin='https://home-lan.jos-dev.ru'):
                nonlocal cookie
                raw=json.dumps(data or {}).encode(); out={}
                env={'HTTP_HOST':'home-lan.jos-dev.ru','REMOTE_ADDR':'172.22.0.2','HTTP_X_FORWARDED_PROTO':'https',
                     'HTTP_X_FORWARDED_FOR':xff,'PATH_INFO':path,'REQUEST_METHOD':'POST' if data is not None else 'GET',
                     'HTTP_ORIGIN':origin,'HTTP_COOKIE':cookie,'CONTENT_TYPE':'application/json','CONTENT_LENGTH':str(len(raw)),
                     'wsgi.input':io.BytesIO(raw)}
                def start(status,headers):
                    nonlocal cookie
                    out.update(status=int(status.split()[0]),headers=dict(headers))
                    cookie=out['headers']['Set-Cookie'].split(';')[0]
                out['body']=json.loads(b''.join(app(env,start)))
                return out
            session=req()['body']; self.assertTrue(session['trusted_device']); self.assertTrue(session['authenticated'])
            self.assertEqual(req('/api/stats')['body'],{'private':42})
            self.assertEqual(req('/api/stats',xff='192.168.1.80, 8.8.8.8')['status'],401)
            self.assertEqual(req('/api/trusted',xff='192.168.1.81')['status'],403)
            self.assertEqual(req('/api/recover',{'csrf':session['csrf'],'password':'new-recovered-password'},xff='192.168.1.81')['status'],403)
            self.assertEqual(req('/api/recover',{'password':'new-recovered-password'})['status'],403)
            self.assertEqual(req('/api/recover',{'csrf':session['csrf'],'password':'new-recovered-password'},origin='https://evil.invalid')['status'],403)
            self.assertTrue(auth.verify('rotated-fixture-password'))
            self.assertEqual(req('/api/recover',{'csrf':session['csrf'],'password':'new-recovered-password'})['status'],200)
            self.assertTrue(auth.verify('new-recovered-password'))
            self.assertEqual(req('/api/stats',xff='8.8.8.8')['status'],401)
            for _ in range(5):
                csrf=req(xff='8.8.8.8')['body']['csrf']
                result=req('/api/login',{'csrf':csrf,'password':'wrong'},xff='8.8.8.8')
            self.assertEqual(result['status'],429)
            self.assertEqual(result['headers']['Retry-After'],'30')


class InventoryTests(unittest.TestCase):
    def test_export_requires_dhcp_and_live_neighbor_agreement(self):
        from dashboard.inventory import build_inventory, collect
        inventory={'hosts':[{'ip':'192.168.1.80','mac':'02:00:00:00:00:80','name':'Fixture phone'}], 'leases':[]}
        line='192.168.1.80 dev br-lan lladdr 02:00:00:00:00:80 REACHABLE'
        result=build_inventory(inventory,line,1000)
        self.assertEqual(result['devices'][0]['name'],'Fixture phone')
        for bad in [line.replace('REACHABLE','STALE'),line.replace('00:80','00:81'),line.replace('br-lan','wan'),'',
                    line+'\n'+line.replace('00:80','00:81')]:
            self.assertEqual(build_inventory(inventory,bad,1000)['devices'],[])
        conflict=inventory|{'leases':[{'ip':'192.168.1.80','mac':'02:00:00:00:00:81','name':'Conflict'}]}
        self.assertEqual(build_inventory(conflict,line,1000)['devices'],[])
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'inventory.json'; commands=[]
            def run(args,**kwargs):
                commands.append(args)
                from types import SimpleNamespace
                return SimpleNamespace(stdout=json.dumps(inventory) if args[-1].endswith('inventory') else line)
            collect('root@192.168.1.1','/test/key',p,run=run,now=lambda:1000)
            self.assertEqual(json.loads(p.read_text())['devices'][0]['mac'],'02:00:00:00:00:80')
            self.assertEqual([cmd[-1] for cmd in commands],['/usr/libexec/home-network-read inventory','/usr/libexec/home-network-read neighbors'])
            self.assertTrue(all(cmd[1:3] == ['-F','/dev/null'] for cmd in commands))
            def fail(*args,**kwargs): raise OSError('router offline')
            with self.assertRaises(OSError): collect('root@192.168.1.1','/test/key',p,run=fail)
            self.assertEqual(json.loads(p.read_text())['devices'],[])


class SecurityConfigTests(unittest.TestCase):
    def test_inventory_is_explicit_opt_in_and_static_security_assets_exist(self):
        from dashboard.__main__ import build_app
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp); Auth(p/'auth','fixture-password')
            env={'DASHBOARD_AUTH_FILE':str(p/'auth'),'DASHBOARD_HISTORY_FILE':str(p/'history'),'DASHBOARD_SPEED_FILE':str(p/'speed')}
            self.assertIsNone(build_app(env).access)
            enabled=build_app(env|{'DASHBOARD_INVENTORY_FILE':str(p/'inventory')})
            self.assertIsNotNone(enabled.access)
            self.assertEqual(enabled.access.path,p/'trusted.json')
            self.assertEqual(enabled.access.macs(),set())
            root=Path(__file__).parent/'dashboard/static'
            self.assertIn('/security.js',(root/'index.html').read_text())
            self.assertTrue((root/'security.js').is_file())  # DOM behavior covered by browser QA


class CooldownTests(unittest.TestCase):
    def test_failed_only_persistent_progressive_cooldown_and_reset(self):
        with tempfile.TemporaryDirectory() as tmp, patch('dashboard.auth.time.time', return_value=1000) as clock:
            path = Path(tmp)/'auth.json'
            auth = Auth(path, 'fixture-password')
            _, session = auth.session()
            for _ in range(8):
                self.assertTrue(auth.login(session, 'fixture-password', 'ignored'))
            for _ in range(4):
                self.assertFalse(auth.login(session, 'wrong', 'ignored'))
            with self.assertRaises(PermissionError) as caught:
                auth.login(session, 'wrong', 'ignored')
            self.assertEqual(caught.exception.retry_after, 30)
            auth = Auth(path)
            _, session = auth.session()
            with self.assertRaises(PermissionError) as caught:
                auth.login(session, 'fixture-password', 'ignored')
            self.assertEqual(caught.exception.retry_after, 30)
            clock.return_value = 1030
            with self.assertRaises(PermissionError) as caught:
                auth.login(session, 'wrong', 'ignored')
            self.assertEqual(caught.exception.retry_after, 60)
            clock.return_value = 1090
            self.assertTrue(auth.login(session, 'fixture-password', 'ignored'))
            self.assertEqual(auth.state['failures'], 0)
            for _ in range(4): self.assertFalse(auth.login(session, 'wrong', 'ignored'))
            for delay in [30,60,120,240,480,960,1920,3600,3600]:
                with self.assertRaises(PermissionError) as caught: auth.login(session, 'wrong', 'ignored')
                self.assertEqual(caught.exception.retry_after, delay)
                clock.return_value += delay
