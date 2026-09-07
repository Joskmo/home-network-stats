"""Small same-origin WSGI surface; deny network data until password rotation."""
import hmac
import ipaddress
import json
from http import HTTPStatus
from http.cookies import SimpleCookie, CookieError
from pathlib import Path
from .topology import Conflict, MAX_BYTES
from .auth import RateLimited
from .access import AccessDenied

STATIC = Path(__file__).with_name('static')
LOCAL_HOSTS = {'localhost', '127.0.0.1', '[::1]'}


def private_lan_request(env, trusted_proxy, lan_network, host):
    """Opt-in TLS LAN ingress; trust forwarded IP only from one pinned proxy.

    Traefik must ALSO enforce ipAllowList using direct peer IP (no ipStrategy).
    Keep forwardedHeaders.insecure=false and do not trust arbitrary upstreams.
    """
    try:
        if not trusted_proxy or ipaddress.ip_address(env.get('REMOTE_ADDR','')) != ipaddress.ip_address(trusted_proxy): return False
        if env.get('HTTP_HOST','').lower() != host or env.get('HTTP_X_FORWARDED_PROTO') != 'https': return False
        client = env.get('HTTP_X_FORWARDED_FOR','').split(',')[-1].strip()
        return ipaddress.ip_address(client) in ipaddress.ip_network(lan_network)
    except ValueError: return False


class Application:
    def __init__(self, auth, stats, public_enabled=False, public_host='home-lan.jos-dev.ru', trusted_lan_proxy='', lan_network='192.168.1.0/24', topology=None, access=None):
        self.auth, self.stats = auth, stats
        self.topology = topology
        self.access = access
        self.public_enabled, self.public_host = public_enabled, public_host
        self.trusted_lan_proxy, self.lan_network = trusted_lan_proxy, lan_network

    def __call__(self, env, start):
        status, body, kind, token = 200, {}, 'application/json', None
        retry_after = 60
        host = env.get('HTTP_HOST','').lower()
        local_host = (host[:host.index(']')+1] if host.startswith('[') and ']' in host else host.split(':')[0]) in LOCAL_HOSTS
        local = local_host and env.get('REMOTE_ADDR') in {'127.0.0.1','::1'} and not any(
            env.get(k) for k in ('HTTP_FORWARDED','HTTP_X_FORWARDED_FOR','HTTP_X_REAL_IP'))
        public = self.public_enabled and host == self.public_host and not self.auth.state['must_change']
        lan = private_lan_request(env,self.trusted_lan_proxy,self.lan_network,self.public_host)
        try:
            if not (local or lan or public):
                status, body = 403, {'error':'private_setup_only'}
            else:
                cookie = SimpleCookie()
                try: cookie.load(env.get('HTTP_COOKIE',''))
                except CookieError: pass
                existing = cookie.get('hn_session')
                token, session = self.auth.session(existing.value if existing else None)
                trusted = bool(self.access and self.access.identity(env))
                path, method = env.get('PATH_INFO','/'), env.get('REQUEST_METHOD','GET')
                if method == 'POST':
                    length = int(env.get('CONTENT_LENGTH') or 0)
                    limit = MAX_BYTES if path in {'/api/topology','/api/topology/preview'} else 4096
                    if not 0 < length <= limit or env.get('CONTENT_TYPE','').split(';')[0] != 'application/json':
                        raise ValueError('Invalid request')
                    payload = json.loads(env['wsgi.input'].read(length))
                    expected_origin = ('http://' + host) if local else ('https://' + self.public_host)
                    origin_ok = env.get('HTTP_ORIGIN') == expected_origin or (local and env.get('HTTP_ORIGIN') == 'https://'+host)
                    if not origin_ok or not isinstance(payload,dict) or not isinstance(payload.get('csrf'),str) or not hmac.compare_digest(payload['csrf'],session['csrf']):
                        status, body = 403, {'error':'csrf_failed'}
                    elif path == '/api/login':
                        password = payload.get('password','')
                        if not isinstance(password,str) or len(password)>256: raise ValueError('Invalid password')
                        if self.auth.login(session,password,env.get('REMOTE_ADDR')):
                            token, session = self.auth.rotate(token)
                            body = self.session_info(session, trusted)
                        else: status, body = 401, {'error':'invalid_password'}
                    elif path == '/api/trusted':
                        if not self.access: raise AccessDenied('Unavailable')
                        self.access.update(self.auth,session,env,payload.get('action'),payload.get('device_id'))
                        body = {'ok':True}
                    elif path == '/api/recover':
                        if not self.access: raise AccessDenied('Unavailable')
                        token = self.access.recover(self.auth,session,env,payload.get('password'))
                        session = self.auth.sessions[token]
                        body = self.session_info(session, trusted)
                    elif path == '/api/password':
                        if not session['authenticated']: status, body = 401, {'error':'login_required'}
                        else:
                            password = payload.get('password','')
                            if not isinstance(password,str): raise ValueError('Invalid password')
                            token = self.auth.change(session,password)
                            body = self.session_info(self.auth.sessions[token])
                    elif path in {'/api/topology','/api/topology/preview'}:
                        if not session['authenticated'] and not trusted: status, body = 401, {'error':'login_required'}
                        elif not self.auth.allowed(session) and not trusted: status, body = 403, {'error':'password_change_required'}
                        elif self.topology is None: status, body = 503, {'error':'temporarily_unavailable'}
                        elif path == '/api/topology/preview':
                            from .discovery import preview
                            body = preview(self.topology, payload.get('topology'))
                        else: body = self.topology.save(payload.get('topology'))
                    elif path == '/api/logout':
                        self.auth.logout(token)
                        token, session = self.auth.session()
                        body = self.session_info(session, trusted)
                    else: status, body = 404, {'error':'not_found'}
                elif method != 'GET': status, body = 405, {'error':'method_not_allowed'}
                elif path == '/api/session': body = self.session_info(session, trusted)
                elif path == '/api/trusted':
                    if not self.access or not self.access.can_manage(self.auth,session,env): raise AccessDenied('Forbidden')
                    devices = self.access.devices()
                    macs = self.access.macs()
                    body = {'devices':[row|{'trusted':row['mac'] in macs} for row in devices],
                            'trusted':[next((row for row in devices if row['mac']==mac),
                                {'id':mac,'name':'…'+mac[-8:],'ip':'','offline':True}) for mac in sorted(macs)]}
                elif path == '/api/topology':
                    if not session['authenticated'] and not trusted: status, body = 401, {'error':'login_required'}
                    elif not self.auth.allowed(session) and not trusted: status, body = 403, {'error':'password_change_required'}
                    elif self.topology is None: status, body = 503, {'error':'temporarily_unavailable'}
                    else: body = self.topology.snapshot()
                elif path == '/api/stats':
                    if not session['authenticated'] and not trusted: status, body = 401, {'error':'login_required'}
                    elif not self.auth.allowed(session) and not trusted: status, body = 403, {'error':'password_change_required'}
                    else: body = self.stats()
                elif path in {'/', '/app.js', '/style.css', '/favicon.svg', '/topology.js', '/topology.css', '/security.js', '/security.css'}:
                    filename, kind = {'/security.js':('security.js','application/javascript'),'/security.css':('security.css','text/css'),'/topology.js':('topology.js','application/javascript'),'/topology.css':('topology.css','text/css'),'/':('index.html','text/html'),'/app.js':('app.js','application/javascript'),'/style.css':('style.css','text/css'),'/favicon.svg':('favicon.svg','image/svg+xml')}[path]
                    # Static shell never contains or embeds network data.
                    file = STATIC / filename
                    body = file.read_bytes() if file.exists() else b'<!doctype html><title>Private network</title>'
                else: status, body = 404, {'error':'not_found'}
        except AccessDenied:
            status, body = 403, {'error':'trusted_device_or_admin_required'}
        except RateLimited as exc:
            retry_after = exc.retry_after
            status, body = 429, {'error':'rate_limited','retry_after':retry_after}
        except Conflict:
            status, body = 409, {'error':'topology_conflict'}
        except PermissionError:
            status, body = 429, {'error':'rate_limited'}
        except (ValueError, TypeError, UnicodeError):
            status, body = 400, {'error':'invalid_request_or_password'}
        except Exception:
            # No stack traces, database paths, router identifiers or secrets to clients.
            status, body = 503, {'error':'temporarily_unavailable'}
        raw = body if isinstance(body,bytes) else json.dumps(body,ensure_ascii=False).encode()
        headers = [('Content-Type',kind+'; charset=utf-8'),('Content-Length',str(len(raw))),
            ('Cache-Control','no-store'),('X-Content-Type-Options','nosniff'),
            ('Referrer-Policy','no-referrer'),('X-Frame-Options','DENY'),
            ('Content-Security-Policy',"default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"),
            ('Permissions-Policy','camera=(), microphone=(), geolocation=()')]
        if public: headers.append(('Strict-Transport-Security','max-age=31536000'))
        if token: headers.append(('Set-Cookie',f'hn_session={token}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=3600'))
        if status == 429: headers.append(('Retry-After',str(retry_after)))
        start(f'{status} {HTTPStatus(status).phrase}', headers)
        return [raw]

    def session_info(self, session, trusted=False):
        return {'authenticated':session['authenticated'] or trusted,
                'password_authenticated':self.auth.allowed(session), 'trusted_device':trusted,
                'must_change':self.auth.state['must_change'] and not trusted, 'csrf':session['csrf']}
