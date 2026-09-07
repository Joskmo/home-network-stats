"""Single-user scrypt authentication. No credentials or signing keys in source."""
import hashlib
import hmac
import json
import os
import secrets
import stat
import threading
import time
from pathlib import Path


class RateLimited(PermissionError):
    def __init__(self, retry_after):
        import math
        self.retry_after = max(1, math.ceil(retry_after))
        super().__init__('Too many attempts; retry later')


class Auth:
    TTL = 3600

    def __init__(self, path, bootstrap=None):
        self.path = Path(path)
        self.lock = threading.RLock()
        self.sessions = {}
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.path.exists():
            info = self.path.stat()
            if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.getuid():
                raise ValueError('Auth state must be an owner-only regular file')
            self.state = json.loads(self.path.read_text())
        else:
            if not bootstrap: raise ValueError('A private bootstrap password file is required on first start')
            self.state = self._hash(bootstrap) | {'must_change': True}
            self._save()

    @staticmethod
    def _hash(password, salt=None):
        salt = salt or secrets.token_hex(16)
        digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
        return {'salt': salt, 'hash': digest}

    def _save(self):
        temp = self.path.with_suffix('.tmp')
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as out:
            json.dump(self.state, out)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, self.path)

    def verify(self, password):
        return hmac.compare_digest(self._hash(password, self.state['salt'])['hash'], self.state['hash'])

    def session(self, token=None):
        with self.lock:
            now = time.monotonic()
            self.sessions = {k:v for k,v in self.sessions.items() if v['expires'] > now}
            if token in self.sessions: return token, self.sessions[token]
            # Anonymous sessions are short-lived and bounded to resist memory exhaustion.
            if len(self.sessions) >= 1024:
                oldest = min(self.sessions, key=lambda k:self.sessions[k]['expires'])
                del self.sessions[oldest]
            token = secrets.token_urlsafe(32)
            session = {'csrf': secrets.token_urlsafe(32), 'authenticated': False, 'expires': now+600}
            self.sessions[token] = session
            return token, session

    def allowed(self, session):
        return bool(session.get('authenticated') and not self.state['must_change'] and session['expires'] > time.monotonic()
                    and any(value is session for value in self.sessions.values()))

    def login(self, session, password, peer):
        # Persist global FAILED attempts; restart and IP rotation cannot bypass it.
        # Wall time is required across restarts. No sleeps or blocked worker waits.
        with self.lock:
            now = time.time()
            remaining = self.state.get('blocked_until', 0) - now
            if remaining > 0: raise RateLimited(remaining)
            if not self.verify(password):
                failures = min(32, self.state.get('failures', 0) + 1)
                delay = min(3600, 30 * 2 ** (failures-5)) if failures >= 5 else 0
                self.state.update(failures=failures, blocked_until=now+delay if delay else 0)
                self._save()
                if delay: raise RateLimited(delay)
                return False
            self.state.update(failures=0, blocked_until=0)
            self._save()
            session['authenticated'] = True
            session['expires'] = time.monotonic()+self.TTL
            return True

    def rotate(self, old):
        with self.lock:
            session = self.sessions.pop(old)
            token = secrets.token_urlsafe(32)
            session['csrf'] = secrets.token_urlsafe(32)
            self.sessions[token] = session
            return token, session

    def change(self, session, password):
        if not session.get('authenticated'): raise PermissionError('Login required')
        if not 12 <= len(password) <= 256 or self.verify(password):
            raise ValueError('Choose a different password of 12–256 characters')
        with self.lock:
            self.state = self._hash(password) | {'must_change': False}
            self._save()
            self.sessions.clear()
            token, fresh = self.session()
            fresh.update(authenticated=True, expires=time.monotonic()+self.TTL)
            return token

    def logout(self, token):
        with self.lock: self.sessions.pop(token, None)
