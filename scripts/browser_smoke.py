"""Teste em navegador com servidor e dados temporários, sem acessar a Meta."""
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parent.parent


def main():
    with TemporaryDirectory() as directory, socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
        sock.close()
        environment = {**os.environ, 'DATA_DIR': directory, 'APP_MODE': 'demo', 'APP_HOST': '127.0.0.1',
                       'APP_PORT': str(port), 'AI_API_KEY': '', 'META_ACCESS_TOKEN': '', 'APP_PASSWORD': ''}
        python = ROOT / '.venv' / 'bin' / 'python'
        server = subprocess.Popen([str(python), '-m', 'app'], cwd=ROOT, env=environment,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            base_url = f'http://127.0.0.1:{port}'
            deadline = time.monotonic() + 15
            while True:
                try:
                    with urllib.request.urlopen(base_url + '/health', timeout=1):
                        break
                except (urllib.error.URLError, TimeoutError):
                    if time.monotonic() > deadline:
                        raise RuntimeError('Servidor não iniciou')
                    time.sleep(.1)
            with sync_playwright() as p:
                options = {'headless': True}
                if os.getenv('BROWSER_EXECUTABLE'):
                    options['executable_path'] = os.environ['BROWSER_EXECUTABLE']
                browser = p.chromium.launch(**options)
                context = browser.new_context(viewport={'width':1440,'height':1000}, timezone_id='America/Sao_Paulo')
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(base_url, wait_until='networkidle')
                expect(page.locator('#cover-credit')).to_have_text('Fernando Vaccari Pickhardt--Dev--Web')
                page.locator('.page-heading .create-trigger').first.click()
                page.locator('#topic').fill('Uma estratégia de marketing que começa com escuta')
                page.locator('#generate-button').click()
                expect(page.locator('#edit-dialog')).to_be_visible()
                expect(page.locator('#publish-button')).to_be_disabled()
                page.locator('#edit-caption').fill('Conheça seu público antes de escolher o próximo conteúdo. #MarketingDigital')
                page.locator('#save-post').click()
                expect(page.locator('#toast')).to_contain_text('Alterações salvas')
                page.locator('#approve-post').check()
                expect(page.locator('#schedule-button')).to_be_enabled()
                when = datetime.now(ZoneInfo('America/Sao_Paulo')) + timedelta(minutes=10)
                page.locator('#schedule-at').fill(when.strftime('%Y-%m-%dT%H:%M'))
                page.locator('#schedule-button').click()
                expect(page.locator('#post-state')).to_contain_text('Agendado')
                page.locator('#cancel-schedule').click()
                expect(page.locator('#post-state')).to_contain_text('Rascunho')
                page.locator('#approve-post').check()
                page.locator('#publish-button').click()
                expect(page.locator('#post-state')).to_contain_text('Simulado')
                expect(page.locator('#post-error')).to_contain_text('Nenhum conteúdo foi enviado')
                page.locator('#edit-dialog .close-dialog').click()
                expect(page.locator('#stat-published')).to_have_text('0')
                page.locator('.nav-item[data-view="automation"]').click()
                expect(page.locator('#automation-topics')).not_to_have_value('')
                page.locator('#automation-enabled').check()
                page.locator('#automation-approved').check()
                page.locator('#automation-form button[type=submit]').click()
                expect(page.locator('#automation-state')).to_have_text('Ativa')
                page.locator('#automation-enabled').uncheck()
                page.locator('#automation-form button[type=submit]').click()
                expect(page.locator('#automation-state')).to_have_text('Desativada')
                for view in ['posts','calendar','brand','connection','overview']:
                    page.locator(f'.nav-item[data-view="{view}"]').click()
                    expect(page.locator(f'#view-{view}')).to_be_visible()
                assert not page.evaluate('document.documentElement.scrollWidth > innerWidth'), 'Overflow no desktop'
                page.set_viewport_size({'width':390,'height':844})
                for view in ['overview','posts','calendar','automation','brand','connection']:
                    page.locator(f'.nav-item[data-view="{view}"]').click()
                    expect(page.locator(f'#view-{view}')).to_be_visible()
                    assert not page.evaluate('document.documentElement.scrollWidth > innerWidth'), f'Overflow mobile: {view}'
                assert errors == [], errors
                browser.close()
            print('Browser OK: criação, edição, aprovação, agendamento, cancelamento, simulação, rotina automática e 6 telas no desktop/mobile; zero erros JavaScript.')
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()


if __name__ == '__main__':
    main()
