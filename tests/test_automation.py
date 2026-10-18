from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch
import asyncio
import unittest

import httpx
from fastapi.testclient import TestClient

from app.automation import next_run
from app.config import Settings
from app.content import generate_content, ContentError
from app.main import create_app


class AutomationTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.settings = Settings(data_dir=Path(directory.name))
        self.app = create_app(self.settings, scheduler=False)
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)
        self.body = {'enabled': True, 'time': '10:00', 'days': [0,1,2,3,4,5,6],
                     'topics': ['Planejamento de conteúdo', 'Marketing de conteúdo'], 'objective': 'educate', 'approved': True}

    def due_config(self):
        rule = dict(self.body)
        rule.pop('approved')
        rule.update(approved_at='2026-09-01T00:00:00+00:00', mode='demo', target='demo')
        self.app.state.db.save_automation(rule)
        return datetime(2026, 10, 1, 14, 0, tzinfo=timezone.utc)

    def test_requires_explicit_approval_and_valid_themes(self):
        self.assertEqual(self.client.put('/api/automation', json={**self.body, 'approved': False}).status_code, 422)
        self.assertEqual(self.client.put('/api/automation', json={**self.body, 'topics': ['a']}).status_code, 422)
        self.assertEqual(self.client.put('/api/automation', json={**self.body, 'days': [8]}).status_code, 422)
        response = self.client.put('/api/automation', json=self.body)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()['active'])
        self.assertIsNotNone(response.json()['next_run'])

    def test_full_recurring_generation_and_simulation_runs_once_per_day(self):
        now = self.due_config()
        automator = self.app.state.publisher.automator
        asyncio.run(automator.tick(now))
        asyncio.run(automator.tick(now + timedelta(hours=1)))
        posts = self.app.state.db.posts()
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]['status'], 'simulated')
        self.assertIsNotNone(posts[0]['approved_at'])
        self.assertEqual(self.app.state.db.automation_runs()[0]['status'], 'simulated')
        asyncio.run(automator.tick(now + timedelta(days=1)))
        self.assertEqual(len(self.app.state.db.posts()), 2)

    def test_never_generates_before_approval_or_in_wrong_mode_or_account(self):
        now = self.due_config()
        rule = self.app.state.db.automation()
        rule['approved_at'] = (now + timedelta(days=1)).isoformat()
        self.app.state.db.save_automation(rule)
        asyncio.run(self.app.state.publisher.automator.tick(now))
        self.assertEqual(self.app.state.db.posts(), [])
        rule.update(approved_at='2026-09-01T00:00:00+00:00', target='live:another-account')
        self.app.state.db.save_automation(rule)
        asyncio.run(self.app.state.publisher.automator.tick(now))
        self.assertEqual(self.app.state.db.posts(), [])
        self.assertIsNone(next_run(self.settings, rule))

    def test_changing_brand_revokes_recurring_approval(self):
        self.client.put('/api/automation', json=self.body)
        brand = self.client.get('/api/brand').json()
        self.client.put('/api/brand', json={**brand, 'name': 'Nova marca'})
        rule = self.client.get('/api/automation').json()
        self.assertFalse(rule['active'])
        self.assertIsNone(rule['approved_at'])

    def test_failed_generation_is_recorded_without_repeat(self):
        now = self.due_config()
        with patch('app.automation.generate_content', new=AsyncMock(side_effect=ContentError('bad key'))):
            asyncio.run(self.app.state.publisher.automator.tick(now))
        asyncio.run(self.app.state.publisher.automator.tick(now))
        self.assertEqual(self.app.state.db.posts(), [])
        self.assertEqual(self.app.state.db.automation_runs()[0]['status'], 'failed')

    def test_ai_content_response_and_failure_without_external_calls(self):
        config = replace(self.settings, ai_key='test-ai-key')
        original_client = httpx.AsyncClient
        def handler(request):
            self.assertEqual(request.headers['Authorization'], 'Bearer test-ai-key')
            return httpx.Response(200, json={'choices': [{'message': {'content': '{"title":"Uma ideia útil","caption":"Legenda revisável","alt_text":"Arte tipográfica"}'}}]})
        with patch('app.content.httpx.AsyncClient', side_effect=lambda **kwargs: original_client(**kwargs, transport=httpx.MockTransport(handler))):
            content = asyncio.run(generate_content(config, self.app.state.db.brand(), 'Marketing digital', 'educate'))
            self.assertEqual(content['source'], 'ai')
            self.assertEqual(content['title'], 'Uma ideia útil')
        def rejected(request):
            return httpx.Response(401, json={'error': {'message': 'test-ai-key'}})
        with patch('app.content.httpx.AsyncClient', side_effect=lambda **kwargs: original_client(**kwargs, transport=httpx.MockTransport(rejected))):
            with self.assertRaises(ContentError) as context:
                asyncio.run(generate_content(config, self.app.state.db.brand(), 'Marketing digital', 'educate'))
            self.assertNotIn('test-ai-key', str(context.exception))


if __name__ == '__main__':
    unittest.main()
