"""Ponta a ponta do Estúdio completo, mídia sintética e voz neural local de verdade."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import os
import socket
import sys
import subprocess
import time
import urllib.request
import urllib.error

from playwright.sync_api import sync_playwright,expect

ROOT=Path(__file__).resolve().parent.parent


def main():
    model_root=Path(os.getenv('REELS_TEST_MODEL_DIR',str(ROOT/'.data/reels/models/kokoro')))
    if not (model_root/'kokoro-v1.0.onnx').is_file():raise RuntimeError('Instale a voz Kokoro antes deste teste completo.')
    with TemporaryDirectory() as temporary:
        directory=Path(temporary);data=directory/'data'
        models=data/'reels/models/kokoro';models.mkdir(parents=True)
        for name in ('kokoro-v1.0.onnx','voices-v1.0.bin'):(models/name).symlink_to(model_root/name)
        video=directory/'TESTE-SINTETICO-sem-gameplay.mp4';sound=directory/'tom-sintetico.wav'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=320x180:rate=30','-t','18','-c:v','libx264','-threads','2',str(video)],check=True)
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=220','-t','2',str(sound)],check=True)
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        environment={**os.environ,'DATA_DIR':str(data),'APP_HOST':'127.0.0.1','APP_PORT':str(port),'APP_MODE':'demo',
            'APP_PASSWORD':'studio-browser-test-password','META_ACCESS_TOKEN':'','INSTAGRAM_ACCOUNT_ID':'','AI_API_KEY':'',
            'PUBLIC_BASE_URL':'','REELS_MIN_FREE_MB':'0','REELS_THREADS':'2','REELS_PIPER_MODEL':''}
        with (directory/'server.log').open('wb') as log:
            python=ROOT/'.venv/bin/python'
            if not python.is_file():python=Path(sys.executable)
            server=subprocess.Popen([str(python),'-m','app'],cwd=ROOT,env=environment,stdout=log,stderr=log)
            try:
                base=f'http://127.0.0.1:{port}';deadline=time.monotonic()+15
                while True:
                    try:urllib.request.urlopen(base+'/health',timeout=1).close();break
                    except (urllib.error.URLError,TimeoutError):
                        if time.monotonic()>deadline:raise RuntimeError('Servidor não iniciou')
                        time.sleep(.1)
                with sync_playwright() as p:
                    options={'headless':True}
                    if os.getenv('BROWSER_EXECUTABLE'):options['executable_path']=os.environ['BROWSER_EXECUTABLE']
                    browser=p.chromium.launch(**options);context=browser.new_context(viewport={'width':1440,'height':1000},accept_downloads=True)
                    page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                    page.goto(base);page.locator('input[type=password]').fill(environment['APP_PASSWORD']);page.locator('button[type=submit]').click()
                    page.locator('[data-view=reels]').click();expect(page.locator('#reels-workspace')).to_be_visible()
                    def tab(name):page.locator(f'#studio-tabs button[data-studio-tab={name}]').click()
                    expect(page.locator('#reels-voice')).to_have_value('kokoro')
                    tab('voice');page.locator('#studio-preview').click();expect(page.locator('#studio-preview-status')).to_contain_text('Prévia pronta',timeout=120000)
                    expect(page.locator('#studio-preview-player')).to_be_visible()
                    tab('create');page.locator('#reels-video-files').set_input_files(str(video));page.locator('#reels-music-file').set_input_files(str(sound));page.locator('#reels-effect-file').set_input_files(str(sound));page.locator('#reels-upload-button').click()
                    expect(page.locator('#reels-upload-status')).to_have_text('Importação concluída.',timeout=30000)
                    tab('trailers');expect(page.locator('.studio-preset')).to_have_count(8)
                    page.locator('.studio-preset').filter(has_text='Fantasia cinematográfica').get_by_role('button').click()
                    expect(page.locator('#studio-preset')).to_have_value('fantasia')
                    page.locator('#reels-title').fill('TESTE SINTÉTICO — estudo de edição')
                    page.locator('#reels-script').fill('Estas imagens são um teste sintético de edição e voz. Nenhum gameplay real aparece neste vídeo.')
                    page.locator('#reels-fit').select_option('blur');page.locator('#reels-music').select_option(label=sound.name)
                    page.get_by_text('Roteiro, áudio e legendas',exact=True).click();page.locator('#reels-effect').select_option(label=sound.name)
                    page.locator('#studio-caption-style').select_option('gamer');page.locator('#studio-highlight').fill('teste')
                    page.get_by_text('Selecionar e revisar cortes',exact=True).click();page.locator('#studio-analyze').click()
                    expect(page.locator('#studio-analysis-status')).to_contain_text('Análise técnica concluída',timeout=120000)
                    page.locator('#studio-review-cuts').click();expect(page.locator('[data-cut-start]').first).to_be_visible()
                    with page.expect_response(lambda response:response.url.endswith('/api/reels/jobs') and response.request.method=='POST') as created:
                        page.locator('#reels-generate').click()
                    reel_id=created.value.json()['id']
                    expect(page.locator(f'.reels-job[data-job-id="{reel_id}"]')).to_contain_text('Pronto',timeout=240000)
                    expect(page.locator('#reels-used-script')).to_contain_text('teste sintético')
                    expect(page.locator('#reels-captions')).to_contain_text('-->')
                    reel_id=page.evaluate("window.AutoPostsReels.jobs().find(j=>j.kind==='reel'&&j.status==='ready').id")
                    deadline=time.monotonic()+15
                    while page.locator('#reels-player').evaluate('v=>v.readyState')<1:
                        if time.monotonic()>deadline:raise AssertionError('Vídeo não carregou')
                        page.wait_for_timeout(100)
                    self_meta=page.locator('#reels-player').evaluate('v=>[v.videoWidth,v.videoHeight,Math.round(v.duration)]');assert self_meta==[1080,1920,15],self_meta
                    page.locator('#reels-player').evaluate('v=>v.play()');page.wait_for_timeout(300)
                    assert page.locator('#reels-player').evaluate('v=>v.currentTime')>0
                    with page.expect_download() as downloaded:page.locator('#reels-download').click()
                    final=directory/'trailer-test.mp4';downloaded.value.save_as(final)
                    subprocess.run(['ffmpeg','-v','error','-i',str(final),'-f','null','-'],check=True)
                    if os.getenv('STUDIO_SCREENSHOT'):
                        page.evaluate('window.scrollTo(0,0)');page.screenshot(path=os.environ['STUDIO_SCREENSHOT'],full_page=True)
                    page.locator('#studio-selection').select_option('sequential')
                    tab('automation');page.locator('#studio-schedule-name').fill('Regra de teste desativada');page.locator('#studio-schedule-form button[type=submit]').click()
                    expect(page.locator('#studio-schedules')).to_contain_text('Regra de teste desativada')
                    expect(page.locator('#studio-schedules')).to_contain_text('Pausada')
                    page.locator('#studio-schedules').get_by_role('button',name='Executar agora').click();expect(page.locator('#studio-schedule-history')).to_contain_text('Na fila',timeout=10000)
                    tab('create');expect(page.locator('[data-cancel-id]')).to_have_count(1,timeout=15000);page.locator('[data-cancel-id]').click()
                    expect(page.locator('#reels-jobs')).to_contain_text('Cancelado',timeout=15000)
                    tab('instagram');page.locator('#studio-delivery-register').click();expect(page.locator('#studio-deliveries')).to_contain_text('Aguardando aprovação')
                    page.locator('#studio-delivery-reviewed').check();page.locator('#studio-delivery-approve').click();expect(page.locator('#studio-deliveries')).to_contain_text('Simulado',timeout=30000)
                    tab('settings');page.locator('[data-limit=reels_upload_mb]').fill('32');page.locator('#studio-limits-form button[type=submit]').click();expect(page.locator('#toast')).to_contain_text('Limites salvos')
                    tab('capture');expect(page.locator('#studio-capture-start')).to_be_visible()
                    with page.expect_download() as package:page.get_by_text('Baixar pacote de câmeras Luau',exact=True).click()
                    package.value.save_as(directory/'capture.rbxmx');assert (directory/'capture.rbxmx').stat().st_size>5000
                    page.set_viewport_size({'width':390,'height':844})
                    for name in ('create','trailers','capture','library','voice','automation','instagram','settings'):
                        tab(name);assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),name
                    page.set_viewport_size({'width':1440,'height':1000});tab('create')
                    page.locator(f'.reels-job[data-job-id="{reel_id}"]').get_by_role('button',name='Limpar intermediários').click();expect(page.locator('#toast')).to_contain_text('preservados')
                    assert context.request.get(base+f'/api/reels/jobs/{reel_id}/download').status==200
                    page.locator('#logout').click()
                    page.wait_for_url('**/login');expect(page.locator('input[type=password]')).to_be_visible()
                    assert context.request.get(base+'/api/reels/instagram/config').status==401
                    assert not errors,errors
                    browser.close()
                    print('Estúdio completo OK: voz neural real, presets, análise, cortes revisados, blur/dissolve, música/SFX, render 1080×1920, reprodução, download, regra persistente desativada, cancelamento, aprovação/simulação, limites, pacote Luau e 8 telas móveis. Nenhum gameplay ou envio Meta real.')
            except BaseException:
                print((directory/'server.log').read_text(errors='replace')[-6000:]);raise
            finally:
                server.terminate()
                try:server.wait(timeout=15)
                except subprocess.TimeoutExpired:server.kill();server.wait()

if __name__=='__main__':main()
