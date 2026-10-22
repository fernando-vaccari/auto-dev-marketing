"""Ponta a ponta pelo navegador: captura sintética, upload, render real e cancelamento."""
from pathlib import Path
from tempfile import TemporaryDirectory
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parent.parent


def main():
    with TemporaryDirectory() as temporary:
        directory=Path(temporary)
        video=directory/'captura-sintetica.mp4'
        music=directory/'trilha-sintetica.wav'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=320x180:rate=30','-t','16',
                        '-c:v','libx264','-threads','2','-pix_fmt','yuv420p',str(video)],check=True)
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=220','-t','2',str(music)],check=True)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        password='browser-test-local-password'
        environment={**os.environ,'DATA_DIR':str(directory/'data'),'APP_MODE':'demo','APP_HOST':'127.0.0.1',
                     'APP_PORT':str(port),'APP_PASSWORD':password,'AI_API_KEY':'','META_ACCESS_TOKEN':'',
                     'REELS_MIN_FREE_MB':'0','REELS_THREADS':'2'}
        with (directory/'server.log').open('wb') as log:
            python=ROOT/'.venv/bin/python'
            if not python.is_file(): python=Path(sys.executable)
            server=subprocess.Popen([str(python),'-m','app'],cwd=ROOT,env=environment,stdout=log,stderr=log)
            try:
                base=f'http://127.0.0.1:{port}'
                deadline=time.monotonic()+15
                while True:
                    try:
                        urllib.request.urlopen(base+'/health',timeout=1).close();break
                    except (urllib.error.URLError,TimeoutError):
                        if time.monotonic()>deadline: raise RuntimeError('Servidor não iniciou')
                        time.sleep(.1)
                with sync_playwright() as p:
                    options={'headless':True}
                    if os.getenv('BROWSER_EXECUTABLE'): options['executable_path']=os.environ['BROWSER_EXECUTABLE']
                    browser=p.chromium.launch(**options)
                    context=browser.new_context(viewport={'width':1440,'height':1000},accept_downloads=True)
                    page=context.new_page();errors=[]
                    page.on('pageerror',lambda err:errors.append(str(err)))
                    page.goto(base)
                    page.locator('input[type=password]').fill(password)
                    page.locator('button[type=submit]').click()
                    expect(page.locator('.nav-item[data-view=reels]')).to_be_visible()
                    page.locator('.nav-item[data-view=reels]').click()
                    expect(page.locator('#reels-workspace')).to_be_visible()
                    page.locator('#reels-video-files').set_input_files(str(video))
                    page.locator('#reels-music-file').set_input_files(str(music))
                    page.locator('#reels-upload-button').click()
                    expect(page.locator('#reels-upload-status')).to_have_text('Importação concluída.',timeout=30000)
                    expect(page.locator('#reels-library input[type=checkbox]')).to_be_checked()
                    expect(page.locator('#reels-upload-progress')).to_have_attribute('value','100')
                    page.locator('#reels-title').fill('TESTE SINTÉTICO — sem gameplay Roblox')
                    page.locator('#reels-plan').click()
                    expect(page.locator('#reels-script')).not_to_have_value('',timeout=10000)
                    script='Este é um teste sintético de renderização local. Nenhuma cena de Roblox é mostrada.'
                    page.locator('#reels-script').fill(script)
                    page.locator('#reels-music').select_option(label=music.name)
                    page.locator('#reels-zoom').fill('1')
                    page.locator('#reels-generate').click()
                    expect(page.locator('#reels-result')).to_be_visible()
                    expect(page.locator('#reels-job-status')).to_contain_text('Pronto',timeout=180000)
                    expect(page.locator('#reels-used-script')).to_contain_text(script)
                    expect(page.locator('#reels-captions')).to_contain_text('-->')
                    expect(page.locator('#reels-render-progress')).to_have_attribute('value','100')
                    deadline=time.monotonic()+10
                    while page.locator("#reels-player").evaluate("v => v.readyState") < 1:
                        if time.monotonic()>deadline: raise AssertionError("Metadados do player indisponíveis")
                        page.wait_for_timeout(100)
                    dimensions=page.locator('#reels-player').evaluate('(v) => [v.videoWidth,v.videoHeight,Math.round(v.duration)]')
                    assert dimensions==[1080,1920,15],dimensions
                    page.locator('#reels-player').evaluate('(v) => v.play()')
                    deadline=time.monotonic()+10
                    while page.locator("#reels-player").evaluate("v => v.currentTime") <= 0:
                        if time.monotonic()>deadline: raise AssertionError("Player não iniciou a reprodução")
                        page.wait_for_timeout(100)
                    with page.expect_download() as download:
                        page.locator('#reels-download').click()
                    target=directory/'download.mp4';download.value.save_as(target)
                    subprocess.run(['ffmpeg','-v','error','-i',str(target),'-f','null','-'],check=True)
                    if os.getenv('REELS_SCREENSHOT'):
                        page.evaluate('window.scrollTo(0,0)')
                        page.screenshot(path=os.environ['REELS_SCREENSHOT'], full_page=True)
                    page.get_by_text('Selecionar e revisar cortes', exact=True).click()
                    page.locator('#studio-selection').select_option('sequential')
                    page.locator('#reels-generate').click()
                    expect(page.locator('#reels-jobs .reels-job')).to_have_count(2,timeout=10000)
                    cancel=page.locator('[data-cancel-id]').first
                    expect(cancel).to_be_visible()
                    cancel.click()
                    expect(page.locator('#reels-job-status')).to_contain_text('Cancelado',timeout=10000)
                    page.set_viewport_size({'width':390,'height':844})
                    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Overflow na tela móvel'
                    page.set_viewport_size({'width':1440,'height':1000})
                    page.locator('#logout').click()
                    page.wait_for_url('**/login')
                    expect(page.locator('input[type=password]')).to_be_visible()
                    assert context.request.get(base+'/api/reels/jobs').status==401
                    assert not errors,errors
                    browser.close()
                    print('Reels navegador: login, upload com progresso, seleção, roteiro, trilha, render, reprodução 1080×1920, download, legendas, cancelamento e tela móvel OK.')
            except BaseException:
                print((directory/'server.log').read_text(errors='replace')[-6000:])
                raise
            finally:
                server.terminate()
                try:server.wait(timeout=10)
                except subprocess.TimeoutExpired:server.kill();server.wait()


if __name__=='__main__':main()
