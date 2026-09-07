import copy
import tempfile
import unittest
from pathlib import Path
from dashboard import topology

MAC = '02:00:00:00:00:01'

class DiscoveryTests(unittest.TestCase):
    def test_native_router_identity_becomes_router_without_inventing_cables(self):
        from dashboard import discovery
        native = 'ROUTER 192.168.1.1 02:00:00:00:00:fe\nFDB\n'
        data = discovery.parse({'leases': []}, native, 100)
        self.assertEqual(len(data['devices']), 1)
        row = data['devices'][0]
        self.assertEqual((row['ip'], row['source']), ('192.168.1.1', 'router interface'))
        result = discovery.merge({'revision': 0, 'nodes': [], 'links': []}, data, now=101)
        self.assertEqual(result['nodes'][0]['type'], 'router')
        self.assertEqual(result['links'], [])
        result['nodes'][0].update(type='device', name='My router', ports=['LAN 1'])
        refreshed = discovery.merge(result, data, now=102)
        self.assertEqual(refreshed['nodes'][0]['type'], 'router')
        self.assertEqual(refreshed['nodes'][0]['name'], 'My router')
        self.assertEqual(refreshed['nodes'][0]['ports'], ['LAN 1'])
        for native in ('ROUTER 8.8.8.8 02:00:00:00:00:fe',
                       'ROUTER 192.168.1.1 not-a-mac'):
            self.assertEqual(discovery.parse({}, native, 100)['devices'], [])

    def test_ui_explicit_preview_apply(self):
        js=Path('dashboard/static/topology.js').read_text()
        self.assertIn('Refresh discovered devices',js)
        self.assertIn('/api/topology/preview',js)
        self.assertIn('map-preview',js)

    def test_preview_authenticated_csrf_no_persistence_and_collector(self):
        import io, json, time
        from dashboard.auth import Auth
        from dashboard.web import Application
        from dashboard import discovery
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)
            auth=Auth(path/'auth.json','bootstrap')
            store=topology.TopologyStore(path/'map')
            app=Application(auth,lambda:{},topology=store)
            token,session=auth.session()
            def req(csrf=None):
                raw=json.dumps({'csrf':csrf or session['csrf'],'topology':{'revision':0,'nodes':[],'links':[]}}).encode()
                status=[]
                body=app({'HTTP_HOST':'localhost','REMOTE_ADDR':'127.0.0.1','HTTP_COOKIE':'hn_session='+token,'PATH_INFO':'/api/topology/preview','REQUEST_METHOD':'POST','HTTP_ORIGIN':'http://localhost','CONTENT_TYPE':'application/json','CONTENT_LENGTH':str(len(raw)),'wsgi.input':io.BytesIO(raw)},lambda s,h:status.append(int(s.split()[0])))
                return status[0],json.loads(b''.join(body))
            self.assertEqual(req()[0],401)
            auth.login(session,'bootstrap','127.0.0.1')
            self.assertEqual(req()[0],403)
            token=auth.change(session,'isolated-test-password'); session=auth.sessions[token]
            self.assertEqual(req('bad')[0],403)
            store.directory.mkdir()
            topology.atomic_json(store.directory/'discovery.json',{'sampled_at':time.time(),'devices':[dict(mac=MAC,ip='192.168.1.2',name='test',source='DHCP lease',last_seen=time.time(),attachment='',confidence='unknown')]})
            code,body=req()
            self.assertEqual(code,200)
            self.assertEqual(len(body['nodes']),1)
            self.assertEqual(store.read()['nodes'],[])
            self.assertTrue(hasattr(discovery,'collect'),'read-only collector missing')
            commands=[]
            def run(command,**kwargs):
                from types import SimpleNamespace
                commands.append(command)
                return SimpleNamespace(stdout='{"leases":[]}' if command[-1].endswith(' inventory') else '')
            result=discovery.collect('root@router','/key',store.directory/'discovery.json',run=run,now=lambda:100)
            self.assertEqual(result['devices'],[])
            self.assertEqual(len(commands),2)
            self.assertIn('StrictHostKeyChecking=yes',commands[0])
            def fail(*a,**k): raise OSError('unavailable')
            with self.assertRaises(OSError): discovery.collect('root@router','/key',store.directory/'discovery.json',run=fail)
            self.assertEqual(json.loads((store.directory/'discovery.json').read_text())['sampled_at'],100)

    def test_native_evidence_no_invented_wires_stale_and_duplicates(self):
        from dashboard import discovery
        self.assertTrue(hasattr(discovery,'parse'), 'native parser missing')
        native = 'PORT lan2 0x2\nPORT phy1-ap0 0x6\nFDB\n2 '+MAC+' no 1.23\n6 02:00:00:00:00:02 no 0.0\n2 02:00:00:00:00:ff yes 0.0\nWIFI phy1-ap0\nStation 02:00:00:00:00:02 (on phy1-ap0)\n'
        inventory = {'hosts':[{'mac':MAC,'name':'old','ip':'192.168.1.2'}],'leases':[{'mac':MAC.upper(),'name':'new','ip':'192.168.1.23'}]}
        data = discovery.parse(inventory,native,100)
        self.assertEqual(len(data['devices']),2)
        rows = {r['mac']:r for r in data['devices']}
        self.assertEqual(rows[MAC]['ip'],'192.168.1.23')
        self.assertEqual(rows[MAC]['attachment'],'lan2')
        self.assertIn('intermediate',rows[MAC]['confidence'])
        self.assertEqual(rows['02:00:00:00:00:02']['source'],'iw station')
        empty = {'revision':0,'nodes':[],'links':[]}
        graph = discovery.merge(empty,data,now=101)
        self.assertEqual(graph['links'],[])
        graph['nodes'][0]['name']='override'
        self.assertEqual(discovery.merge(graph,data,now=102)['nodes'][0]['name'],'override')
        with self.assertRaises(ValueError): discovery.merge(empty,data,now=200)
        duplicate = copy.deepcopy(graph['nodes'][0]); duplicate['id']='duplicate'; duplicate['mac']=duplicate['mac'].upper()
        graph['nodes'].append(duplicate)
        with self.assertRaises(ValueError): topology.validate(graph)


    def test_import_matches_mac_updates_ip_preserves_manual_and_history(self):
        from dashboard import discovery
        graph = {'revision':0,'nodes':[dict(id='manual',name='My desktop',type='server',ip='192.168.1.2',mac=MAC.upper(),x=321,y=222),dict(id='switch',name='My switch',type='switch',ip='',mac='',x=20,y=30)],'links':[dict(id='wire',source='manual',target='switch',source_port='NIC',target_port='Port 8')]}
        graph['nodes'][0].update(type='desktop', ports=['NIC'])
        graph['nodes'][1]['ports'] = ['Port 1', 'Port 8']
        graph['links'][0]['medium'] = 'ethernet'
        original = copy.deepcopy(graph)
        snapshot = {'sampled_at':100,'devices':[dict(mac=MAC,ip='192.168.1.23',name='DHCP name',source='DHCP lease',last_seen=100,attachment='lan2',confidence='reachable via; intermediate topology unknown')]}
        self.assertTrue(hasattr(discovery, 'merge'), 'identity-preserving merge missing')
        merged = discovery.merge(graph,snapshot,now=110)
        self.assertEqual(graph,original)
        self.assertEqual(len(merged['nodes']),2)
        node = merged['nodes'][0]
        self.assertEqual((node['id'],node['name'],node['x'],node['y']),('manual','My desktop',321,222))
        self.assertEqual(node['ip'],'192.168.1.23')
        self.assertEqual(node['type'], 'desktop')
        self.assertEqual(node['ports'], ['NIC'])
        self.assertEqual(merged['nodes'][1]['ports'], ['Port 1', 'Port 8'])
        self.assertEqual(merged['links'],graph['links'])
        self.assertEqual(discovery.merge(merged,{'sampled_at':111,'devices':[]},now=112),merged)
        with tempfile.TemporaryDirectory() as tmp:
            store = topology.TopologyStore(tmp)
            store.save(merged)
            self.assertEqual(store.read()['nodes'],merged['nodes'])
