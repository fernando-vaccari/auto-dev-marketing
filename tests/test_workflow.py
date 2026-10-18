from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs
import asyncio
import io
import time
import unittest

import httpx
from fastapi.testclient import TestClient
from PIL import Image

from app.config import Settings
from app.main import create_app
from app.meta import MetaClient


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.settings = Settings(data_dir=Path(self.directory.name))
        self.app = create_app(self.settings, scheduler=False)
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)

    def draft(self, client=None):
        response = (client or self.client).post('/api/posts/generate', json={
            'topic': 'Planejamento de conteúdo para marketing digital', 'objective': 'educate'})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def live(self, handler):
        config = replace(self.settings, mode='live', meta_token='test-token', instagram_id='1234',
                         public_url='https://posts.example.com', password='test-password-long')
        meta = MetaClient(config, transport=httpx.MockTransport(handler), poll_seconds=0, poll_attempts=2)
        app = create_app(config, scheduler=False, meta=meta)
        client = TestClient(app, base_url='https://posts.example.com')
        self.addCleanup(client.close)
        self.assertEqual(client.post('/api/login', json={'password': config.password}).status_code, 200)
        return app, client

    def test_personalized_brand_and_generated_jpeg(self):
        brand = self.client.get('/api/brand').json()
        self.assertEqual(brand['name'], 'Auto Posts')
        self.assertEqual(brand['signature'], 'Fernando Vaccari Pickhardt--Dev--Web')
        post = self.draft()
        self.assertIn('Marketingdigital', post['caption'])
        response = self.client.get('/media/' + post['image'])
        self.assertEqual(response.status_code, 200)
        with Image.open(io.BytesIO(response.content)) as image:
            self.assertEqual(image.format, 'JPEG')
            self.assertEqual(image.size, (1080, 1350))

    def test_demo_publish_requires_approval_and_never_counts_as_real(self):
        post = self.draft()
        path = f"/api/posts/{post['id']}/publish"
        self.assertEqual(self.client.post(path, json={'approved': False}).status_code, 422)
        result = self.client.post(path, json={'approved': True})
        self.assertEqual(result.json()['status'], 'simulated')
        self.assertIsNone(result.json()['media_id'])
        self.assertEqual(self.client.post(path, json={'approved': True}).status_code, 409)
        self.assertEqual(len(self.client.get('/api/events').json()), 3)

    def test_edit_invalidates_approval_and_schedule(self):
        post = self.draft()
        when = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        path = f"/api/posts/{post['id']}"
        scheduled = self.client.post(path + '/schedule', json={'approved': True, 'scheduled_at': when})
        self.assertEqual(scheduled.json()['status'], 'scheduled')
        self.assertIsNotNone(scheduled.json()['approved_at'])
        result = self.client.put(path, json={'title': 'Uma nova ideia', 'caption': 'Uma nova legenda', 'alt_text': 'Uma nova arte'})
        self.assertEqual(result.json()['status'], 'draft')
        self.assertIsNone(result.json()['approved_at'])
        self.assertIsNone(result.json()['scheduled_at'])
        self.assertNotEqual(result.json()['image'], post['image'])

    def test_invalid_dates_and_nonexistent_posts(self):
        post = self.draft()
        for when in ['2020-01-01T10:00:00+00:00', '2030-01-01T10:00:00']:
            response = self.client.post(f"/api/posts/{post['id']}/schedule", json={'approved': True, 'scheduled_at': when})
            self.assertEqual(response.status_code, 422)
        self.assertEqual(self.client.post('/api/posts/missing/publish', json={'approved': True}).status_code, 404)
        self.assertEqual(self.client.post('/api/posts/generate', json={'topic': 'a'}).status_code, 422)

    def test_upload_converts_png_and_rejects_invalid_ratio(self):
        post = self.draft()
        path = f"/api/posts/{post['id']}/image"
        for size, expected in [((1080, 1080), 200), ((100, 1000), 422)]:
            buffer = io.BytesIO()
            Image.new('RGB', size, '#7454e9').save(buffer, 'PNG')
            response = self.client.post(path, content=buffer.getvalue())
            self.assertEqual(response.status_code, expected, response.text)
        self.assertEqual(self.client.post(path, content=b'not an image').status_code, 422)
        self.assertEqual(self.client.post(path, content=b'x' * 8_000_001).status_code, 413)

    def test_scheduler_processes_only_due_approved_posts_and_persists(self):
        post, future, unapproved = self.draft(), self.draft(), self.draft()
        db = self.app.state.db
        db.schedule(post['id'], '2020-01-01T00:00:00+00:00', 'demo')
        db.schedule(future['id'], '2099-01-01T00:00:00+00:00', 'demo')
        with db.connect() as conn:
            conn.execute("UPDATE posts SET status='scheduled',scheduled_at=? WHERE id=?", ('2020-01-01T00:00:00+00:00', unapproved['id']))
        asyncio.run(self.app.state.publisher.tick())
        self.assertEqual(db.get(post['id'])['status'], 'simulated')
        self.assertEqual(db.get(future['id'])['status'], 'scheduled')
        self.assertEqual(db.get(unapproved['id'])['status'], 'scheduled')
        restarted = create_app(self.settings, scheduler=False)
        self.assertEqual(restarted.state.db.get(post['id'])['status'], 'simulated')

    def test_actual_background_scheduler_and_cancel(self):
        post = self.draft()
        db = self.app.state.db
        db.schedule(post['id'], '2020-01-01T00:00:00+00:00', 'demo')
        application = create_app(replace(self.settings, scheduler_seconds=.02))
        with TestClient(application):
            deadline = time.monotonic() + 3
            while db.get(post['id'])['status'] != 'simulated' and time.monotonic() < deadline:
                time.sleep(.02)
            self.assertEqual(db.get(post['id'])['status'], 'simulated')
        another = self.draft()
        db.schedule(another['id'], '2099-01-01T00:00:00+00:00', 'demo')
        response = self.client.post(f"/api/posts/{another['id']}/cancel")
        self.assertEqual(response.json()['status'], 'draft')
        self.assertIsNone(response.json()['approved_at'])

    def test_atomic_claim_prevents_duplicate_workers(self):
        post = self.draft()
        with ThreadPoolExecutor(max_workers=5) as pool:
            claims = list(pool.map(lambda _: self.app.state.db.claim(post['id'], 'demo'), range(5)))
        self.assertEqual(sum(item is not None for item in claims), 1)

    def test_restart_marks_interrupted_publish_for_manual_review(self):
        post = self.draft()
        self.app.state.db.claim(post['id'], 'live')
        with TestClient(create_app(self.settings)):
            self.assertEqual(self.app.state.db.get(post['id'])['status'], 'review_required')

    def test_mode_switch_never_publishes_demo_approvals(self):
        def handler(request):
            self.fail('Nenhuma chamada à Meta era esperada')
        app, _ = self.live(handler)
        post = self.draft()
        app.state.db.schedule(post['id'], '2020-01-01T00:00:00+00:00', 'demo')
        asyncio.run(app.state.publisher.tick())
        self.assertEqual(app.state.db.get(post['id'])['status'], 'scheduled')

    def test_meta_full_create_poll_publish_flow(self):
        calls = []
        def handler(request):
            calls.append((request.method, request.url.path))
            self.assertEqual(request.headers['Authorization'], 'Bearer test-token')
            self.assertNotIn('access_token', request.url.params)
            if request.url.path.endswith('/1234/media'):
                fields = parse_qs(request.content.decode())
                self.assertTrue(fields['image_url'][0].startswith('https://posts.example.com/media/'))
                self.assertIn('caption', fields)
                return httpx.Response(200, json={'id': '5678'})
            if request.url.path.endswith('/5678'):
                return httpx.Response(200, json={'status_code': 'FINISHED'})
            if request.url.path.endswith('/1234/media_publish'):
                self.assertEqual(parse_qs(request.content.decode())['creation_id'], ['5678'])
                return httpx.Response(200, json={'id': '9012'})
            return httpx.Response(200, json={'id': '1234', 'username': 'auto_posts'})
        app, client = self.live(handler)
        post = self.draft(client)
        result = client.post(f"/api/posts/{post['id']}/publish", json={'approved': True}).json()
        self.assertEqual(result['status'], 'published')
        self.assertEqual(result['media_id'], '9012')
        self.assertEqual(result['container_id'], '5678')
        self.assertEqual(len(calls), 3)
        self.assertEqual(client.post('/api/meta/test').json()['username'], 'auto_posts')

    def test_meta_timeout_after_publish_needs_manual_review_and_cannot_retry(self):
        def handler(request):
            if request.url.path.endswith('/media_publish'):
                raise httpx.ReadTimeout('untrusted secret text', request=request)
            if request.method == 'POST':
                return httpx.Response(200, json={'id': '5678'})
            return httpx.Response(200, json={'status_code': 'FINISHED'})
        app, client = self.live(handler)
        post = self.draft(client)
        path = f"/api/posts/{post['id']}/publish"
        result = client.post(path, json={'approved': True}).json()
        self.assertEqual(result['status'], 'review_required')
        self.assertNotIn('untrusted secret text', result['error'])
        self.assertEqual(client.post(path, json={'approved': True}).status_code, 409)

    def test_meta_expired_token_and_invalid_responses_are_sanitized(self):
        def handler(request):
            return httpx.Response(400, json={'error': {'code': 190, 'message': 'untrusted-secret'}})
        _, client = self.live(handler)
        post = self.draft(client)
        result = client.post(f"/api/posts/{post['id']}/publish", json={'approved': True}).json()
        self.assertEqual(result['status'], 'failed')
        self.assertIn('token', result['error'])
        self.assertNotIn('untrusted-secret', result['error'])
        meta = MetaClient(self.settings, transport=httpx.MockTransport(lambda _: httpx.Response(200, json=[])))
        with self.assertRaisesRegex(Exception, 'Formato inesperado'):
            asyncio.run(meta.account())

    def test_login_csrf_session_forgery_and_rate_limit(self):
        config = replace(self.settings, password='a-long-test-password')
        with TestClient(create_app(config, scheduler=False)) as client:
            self.assertEqual(client.get('/api/posts').status_code, 401)
            client.cookies.set('session', '1234.forged')
            self.assertEqual(client.get('/api/posts').status_code, 401)
            client.cookies.clear()
            self.assertEqual(client.post('/api/login', json={'password': config.password}, headers={'origin': 'https://evil.example'}).status_code, 403)
            self.assertEqual(client.post('/api/login', json={'password': config.password}).status_code, 200)
            self.assertEqual(client.get('/api/posts').status_code, 200)
            self.assertEqual(client.put('/api/brand', json=self.app.state.db.brand(), headers={'origin': 'https://evil.example'}).status_code, 403)
            cookie = client.cookies.get('session')
            client.post('/api/logout')
            self.assertEqual(client.get('/api/posts').status_code, 401)
            for _ in range(5):
                self.assertEqual(client.post('/api/login', json={'password': 'wrong'}).status_code, 401)
            self.assertEqual(client.post('/api/login', json={'password': 'wrong'}).status_code, 429)
        with TestClient(create_app(replace(config, password='new-test-password'), scheduler=False)) as changed:
            changed.cookies.set('session', cookie)
            self.assertEqual(changed.get('/api/posts').status_code, 401)

    def test_live_configuration_fails_closed_and_secrets_are_not_exposed(self):
        with self.assertRaisesRegex(ValueError, 'META_ACCESS_TOKEN'):
            create_app(replace(self.settings, mode='live'))
        def handler(request):
            return httpx.Response(200, json={})
        _, client = self.live(handler)
        self.assertNotIn('test-token', client.get('/api/status').text)
        self.assertNotIn('test-password-long', client.get('/api/status').text)
        for endpoint in ['/', '/static/app.js', '/static/style.css', '/health']:
            response = client.get(endpoint)
            self.assertEqual(response.status_code, 200, endpoint)
            self.assertIn("default-src 'self'", response.headers['content-security-policy'])


if __name__ == '__main__':
    unittest.main()
