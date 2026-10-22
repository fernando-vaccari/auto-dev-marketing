"""Microfone real do navegador com entrada sintética: não comprova clonagem neural."""
from pathlib import Path
from tempfile import TemporaryDirectory
import os
import socket
import subprocess
import sys
import time
import urllib.request
from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]


def main():
    with TemporaryDirectory() as temporary:
        directory=Path(temporary);audio=directory/'microfone-sintetico.wav'
        raw=directory/'fala-sintetica.wav'
        subprocess.run([os.environ.get('REELS_ESPEAK_NG','espeak-ng'),'-v','pt-br','-s','150','-w',str(raw),'Esta gravação sintética serve apenas para testar o microfone do navegador. Não é uma voz humana nem uma clonagem. O teste verifica consentimento, envio privado e validação de uma amostra de áudio local.'],check=True)
        subprocess.run(['ffmpeg','-v','error','-i',str(raw),'-ar','48000',str(audio)],check=True)
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        environment={**os.environ,'DATA_DIR':str(directory/'data'),'APP_HOST':'127.0.0.1','APP_PORT':str(port),
                     'APP_PASSWORD':'test-my-voice-browser','APP_MODE':'demo','REELS_MIN_FREE_MB':'0',
                     'META_ACCESS_TOKEN':'','INSTAGRAM_ACCOUNT_ID':'','AI_API_KEY':''}
        with (directory/'server.log').open('wb') as log:
            python=ROOT/'.venv/bin/python'
            if not python.is_file():python=Path(sys.executable)
            server=subprocess.Popen([str(python),'-m','app'],cwd=ROOT,env=environment,stdout=log,stderr=log)
            base=f'http://127.0.0.1:{port}'
            try:
                deadline=time.monotonic()+30
                while True:
                    try:urllib.request.urlopen(base+'/health',timeout=1).close();break
                    except OSError:
                        if time.monotonic()>deadline:raise
                        time.sleep(.1)
                with sync_playwright() as p:
                    options={'headless':True,'args':['--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream','--use-file-for-fake-audio-capture='+str(audio)]}
                    if os.getenv('BROWSER_EXECUTABLE'):options['executable_path']=os.environ['BROWSER_EXECUTABLE']
                    browser=p.chromium.launch(**options);context=browser.new_context(permissions=['microphone'],viewport={'width':1280,'height':900})
                    page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    page.goto(base);page.locator('input[type=password]').fill(environment['APP_PASSWORD']);page.locator('button[type=submit]').click()
                    page.locator('.nav-item[data-view=reels]').click();page.locator('[data-studio-tab=my-voice]').click()
                    expect(page.locator('#my-voice-runtime')).to_contain_text('OpenVoice')
                    page.locator('#my-voice-file').set_input_files(str(audio));expect(page.locator('#my-voice-local-player')).to_be_visible()
                    page.locator('#my-voice-save').click();expect(page.locator('#my-voice-status')).to_contain_text('Confirme a autorização')
                    page.locator('#my-voice-consent').check()
                    with page.expect_response(lambda response:'/api/reels/my-voice?' in response.url and response.request.method=='POST') as saved:
                        page.locator('#my-voice-save').click()
                    assert saved.value.status==201,saved.value.text()
                    expect(page.locator('#my-voice-status')).to_contain_text('Perfil salvo',timeout=30000)
                    expect(page.locator('#my-voice-profiles audio')).to_have_count(1)
                    page.locator('#my-voice-record').click();expect(page.locator('#my-voice-stop')).to_be_enabled()
                    page.wait_for_timeout(8500);page.locator('#my-voice-stop').click()
                    expect(page.locator('#my-voice-local-player')).to_be_visible();expect(page.locator('#my-voice-record')).to_be_enabled()
                    page.locator('#my-voice-name').fill('Microfone sintético')
                    with page.expect_response(lambda response:'/api/reels/my-voice?' in response.url and response.request.method=='POST') as saved:
                        page.locator('#my-voice-save').click()
                    assert saved.value.status==201,saved.value.text()
                    expect(page.locator('#my-voice-profiles audio')).to_have_count(2,timeout=30000)
                    expect(page.locator('#my-voice-status')).to_contain_text('Perfil salvo')
                    page.locator('#my-voice-use').click();expect(page.locator('#my-voice-status')).to_contain_text('Gere uma prévia')
                    page.set_viewport_size({'width':390,'height':844});page.wait_for_timeout(100)
                    assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth'),'Overflow horizontal'
                    page.locator('#my-voice-profiles button').first.click();expect(page.locator('#my-voice-profiles audio')).to_have_count(1)
                    page.locator('#my-voice-profiles button').first.click();expect(page.locator('#my-voice-profiles audio')).to_have_count(0)
                    page.set_viewport_size({'width':1280,'height':900})
                    page.locator('#logout').click();page.wait_for_url('**/login')
                    assert context.request.get(base+'/api/reels/my-voice').status==401
                    assert not errors,errors
                    browser.close();print('Minha Voz navegador OK: consentimento, WAV, MediaRecorder WebM, reprodução privada, perfis, exclusão, aprovação obrigatória, mobile e logout. Conversão real não executada sem pesos.')
            except BaseException:
                print((directory/'server.log').read_text(errors='replace')[-3000:]);raise
            finally:
                server.terminate()
                try:server.wait(timeout=15)
                except subprocess.TimeoutExpired:server.kill();server.wait()


if __name__=='__main__':main()
