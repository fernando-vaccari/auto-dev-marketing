/* Estúdio local: reutiliza a sessão e os componentes visuais do painel. */
(() => {
  const q = id => document.getElementById('reels-' + id);
  const statusNames = {queued:'Na fila', rendering:'Renderizando', ready:'Pronto', failed:'Falhou', cancelled:'Cancelado'};
  const stageNames = {queued:'Aguardando execução', preflight:'Verificando ferramentas e arquivos', narration:'Gerando narração', cuts:'Editando cortes', compositing:'Montando vídeo e áudio', validation:'Conferindo MP4', ready:'Concluído', failed:'Falha no processamento', interrupted:'Interrompido', cancelled:'Cancelado'};
  let jobsVersion = '';
  let active = false, loading = false, config, assets = [], jobs = [], selectedJob = null, detailVersion = '', uploading = false;
  const selected = new Set();
  const bytes = value => (value / 1048576).toFixed(1) + ' MB';
  const themes = value => value.split(',').map(s => s.trim()).filter(Boolean);
  const error = err => toast(err.message, true);
  const request = (path, options) => api('/reels' + path, options);
  const busyButton = async (button, action) => { button.disabled = true; try { await action(); } catch (err) { error(err); } finally { button.disabled = false; } };

  function payload() {
    const body = {asset_ids:[...selected], title:q('title').value, duration:Number(q('duration').value), themes:themes(q('themes').value),
      script:q('script').value.trim() || null, tts:q('voice').value, music_id:q('music').value || null,
      fit:q('fit').value, zoom:Number(q('zoom').value)/100};
    return window.AutoPostsStudio ? window.AutoPostsStudio.extendPayload(body) : body;
  }
  function showStorage() {
    if (!config) return;
    q('storage').textContent = `Biblioteca: ${bytes(config.storage.used_bytes)} de ${bytes(config.storage.limit_bytes)}. Limites por arquivo: vídeo ${bytes(config.video_limit_bytes)}, trilha ${bytes(config.music_limit_bytes)}.`;
  }
  function drawLibrary() {
    const container = q('library'); container.replaceChildren();
    for (const item of assets.filter(item => item.kind === 'video')) {
      const row = node('div','reels-asset'); const label = node('label'); const box = node('input');
      box.type = 'checkbox'; box.value = item.id; box.checked = selected.has(item.id);
      box.addEventListener('change', () => { box.checked ? selected.add(item.id) : selected.delete(item.id); });
      label.append(box, document.createTextNode(item.original_name));
      const info = node('small','', `${item.metadata.duration.toFixed(1)} s · ${item.original_name.split('.').pop().toUpperCase()} · ${bytes(item.size_bytes)} · ${item.tags.join(', ')}`);
      row.append(label,info);
      const tags=node('input');tags.value=item.tags.join(', ');tags.maxLength=150;tags.setAttribute('aria-label','Temas de '+item.original_name);
      const save=node('button','secondary','Salvar temas');save.type='button';save.addEventListener('click',()=>busyButton(save,async()=>{await request('/assets/'+item.id,{method:'PATCH',body:{tags:themes(tags.value)}});assets=await request('/assets');drawLibrary();toast('Temas atualizados.');}));
      row.append(tags,save);container.append(row);
    }
    if (!container.children.length) container.append(node('p','help','Importe pelo menos 15 segundos de gravações para começar.'));
    const previous = q('music').value;
    q('music').replaceChildren(new Option('Sem trilha',''));
    for (const item of assets.filter(item => item.kind === 'music')) q('music').append(new Option(item.original_name,item.id));
    q('music').value = previous;
    const effect=q('effect');
    if(effect) { const previousEffect=effect.value; effect.replaceChildren(new Option('Sem efeito sonoro','')); for(const item of assets.filter(item => item.kind === 'effect')) effect.append(new Option(item.original_name,item.id)); effect.value=previousEffect; }
  }
  function drawJobs() {
    const container = q('jobs'); container.replaceChildren();
    for (const job of jobs) {
      const row = node('div','reels-job'); row.dataset.jobId = job.id;
      const info = node('div','reels-job-info'); info.append(node('strong','',(job.kind==='analysis' ? 'Análise · ' : job.kind==='voice_preview' ? 'Prévia de voz · ' : '')+job.config.title),node('small','',`${statusNames[job.status] || job.status} · ${job.progress}% · ${stageNames[job.stage] || job.stage} · ${new Date(job.created_at).toLocaleString('pt-BR')}`));
      const view = node('button','secondary','Ver detalhes'); view.type='button'; view.addEventListener('click',() => { selectedJob=job.id; detailVersion=''; refreshDetail().catch(error); });
      row.append(info,view);
      if (job.origin === 'web' && ['queued','rendering'].includes(job.status)) {
        const cancel = node('button','secondary','Cancelar render'); cancel.type='button'; cancel.dataset.cancelId=job.id;
        cancel.addEventListener('click',() => busyButton(cancel,async () => { await request(`/jobs/${job.id}/cancel`,{method:'POST'}); await refresh(); })); row.append(cancel);
      }
      if(!['queued','rendering'].includes(job.status)) {
        const clean=node('button','secondary','Limpar intermediários'); clean.type='button'; clean.addEventListener('click',()=>busyButton(clean,async()=>{const result=await request(`/jobs/${job.id}/cleanup`,{method:'POST'});toast(`${result.removed_entries} intermediários removidos. Originais e entregáveis preservados.`);}));row.append(clean);
      }
      container.append(row);
    }
    if (!jobs.length) container.append(node('p','help','Seus renders aparecerão aqui. Nenhuma publicação será realizada.'));
  }
  async function refreshDetail() {
    if (!selectedJob) return;
    const job = jobs.find(job => job.id === selectedJob) || await request('/jobs/'+selectedJob);
    q('result').hidden=false; q('result-title').textContent=job.config.title;
    q('job-status').textContent=`${statusNames[job.status] || job.status} · ${stageNames[job.stage] || job.stage} · ${job.progress}%`;
    q('render-progress').value=job.progress; q('job-error').textContent=job.error || '';
    q('events').replaceChildren(...job.events.map(event => node('li','',`${event.progress}% · ${stageNames[event.stage] || event.stage}${event.detail ? ': '+event.detail : ''}`)));
    const audio=q('preview-player');
    audio.hidden=!job.audio_url;
    if(job.audio_url) { if(audio.getAttribute('src')!==job.audio_url) audio.src=job.audio_url; }
    else { audio.pause(); audio.removeAttribute('src'); }
    window.dispatchEvent(new CustomEvent('reels-job',{detail:job}));
    if (job.video_url) {
      if (q('player').getAttribute('src') !== job.video_url) q('player').src=job.video_url;
      q('player').hidden=false; q('download').hidden=false; q('download').href=`/api/reels/jobs/${job.id}/download`;
    } else { q('player').pause(); q('player').removeAttribute('src'); q('player').hidden=true; q('download').hidden=true; }
    const version=job.id+job.updated_at;
    if (detailVersion !== version) {
      const texts=await request(`/jobs/${job.id}/texts`);
      if (selectedJob !== job.id) return;
      q('used-script').textContent=texts.script || 'O roteiro ficará disponível quando a etapa de planejamento terminar.';
      q('captions').textContent=texts.captions || 'As legendas ficarão disponíveis após a narração.';
      detailVersion=version;
    }
  }
  async function refresh() {
    jobs=await request('/jobs');
    const version=jobs.map(job => job.id+job.updated_at+job.status).join('|');
    if (version !== jobsVersion) { drawJobs(); jobsVersion=version; }
    await refreshDetail();
  }
  async function enter() {
    if (loading) return; loading=true;
    try {
      config=await request('/config'); q('notice').textContent='Processamento local e privado. Revise o vídeo exportado antes de qualquer publicação.';
      q('workspace').hidden=false;
      const voice=q('voice').value; q('voice').replaceChildren();
      for (const name of config.voices) q('voice').append(new Option(name === 'kokoro' ? 'Kokoro · voz neural pt-BR' : name === 'piper' ? 'Piper · modelo pt-BR local' : 'eSpeak NG · offline',name));
      if (q('voice').dataset.chosen && config.voices.includes(voice)) q('voice').value=voice;
      else if(config.voices.includes('kokoro')) q('voice').value='kokoro';
      q('generate').disabled=!config.voices.length;
      if (!config.voices.length) q('notice').textContent='Instale as ferramentas locais com scripts/install-reels.sh. Nenhuma voz offline está disponível.';
      assets=await request('/assets'); drawLibrary(); showStorage(); window.dispatchEvent(new CustomEvent('reels-loaded',{detail:config})); await refresh();
    } catch (err) { q('notice').textContent=err.message; q('workspace').hidden=true; }
    finally { loading=false; }
  }
  function upload(file,kind) {
    return new Promise((resolve,reject) => {
      const limit=kind === 'video' ? config.video_limit_bytes : config.music_limit_bytes;
      if (file.size > limit || !file.size) { reject(new Error(`Arquivo vazio ou acima do limite: ${file.name}`)); return; }
      const xhr=new XMLHttpRequest();
      xhr.open('POST','/api/reels/assets?'+new URLSearchParams({filename:file.name,kind,tags:q('upload-tags').value}));
      xhr.setRequestHeader('Content-Type','application/octet-stream');
      xhr.upload.onprogress=event => { if(event.lengthComputable) q('upload-progress').value=event.loaded/event.total*100; };
      xhr.upload.onload=() => { q('upload-status').textContent=`Validando ${file.name}…`; };
      xhr.onerror=() => reject(new Error('Falha de conexão durante o upload.'));
      xhr.onload=() => {
        let data; try { data=JSON.parse(xhr.responseText); } catch { reject(new Error('Resposta inválida durante o upload.')); return; }
        if(xhr.status === 401) { window.location.assign('/login'); reject(new Error('Entre novamente.')); return; }
        if(xhr.status >= 400) { reject(new Error(typeof data.detail === 'string' ? data.detail : 'Upload recusado.')); return; }
        resolve(data);
      };
      q('upload-status').textContent=`Enviando ${file.name}…`; q('upload-progress').value=0; xhr.send(file);
    });
  }
  q('upload-form').addEventListener('submit', event => {
    event.preventDefault(); if(uploading || !config) return;
    busyButton(q('upload-button'),async () => {
      uploading=true;
      try {
        const files=[...q('video-files').files].map(file => [file,'video']);
        if(q('effect-file')?.files[0]) files.push([q('effect-file').files[0],'effect']);
        if(q('music-file').files[0]) files.push([q('music-file').files[0],'music']);
        if(!files.length) throw new Error('Selecione um vídeo ou uma trilha.');
        for(const [file,kind] of files) { const item=await upload(file,kind); if(kind === 'video') selected.add(item.id); }
        q('video-files').value=''; q('music-file').value=''; if(q('effect-file')) q('effect-file').value=''; q('upload-status').textContent='Importação concluída.';
      } finally { uploading=false; assets=await request('/assets'); config=await request('/config'); drawLibrary(); showStorage(); }
    });
  });
  q('plan').addEventListener('click',() => busyButton(q('plan'),async () => {
    const body=payload(); body.script=null; const plan=await request('/plan',{method:'POST',body}); q('script').value=plan.script; toast('Roteiro preparado. Revise antes de gerar.');
  }));
  q('create-form').addEventListener('submit',event => { event.preventDefault(); busyButton(q('generate'),async () => {
    const job=await request('/jobs',{method:'POST',body:payload()}); selectedJob=job.id; detailVersion=''; await refresh(); toast('Reel adicionado à fila local.');
  }); });
  q('voice').addEventListener('change',()=>{q('voice').dataset.chosen='true';});
  window.AutoPostsReels={payload,enter,refresh,assets:()=>assets,jobs:()=>jobs,setSelected:ids=>{selected.clear();for(const id of ids)if(assets.some(a=>a.id===id))selected.add(id);drawLibrary();},selectJob:async id=>{selectedJob=id;detailVersion='';await refresh();}};
  window.addEventListener('workspace-view',event => { active=event.detail === 'reels'; if(active) enter(); });
  setInterval(() => { if(active && !document.hidden && config && !loading) { loading=true; refresh().catch(error).finally(() => { loading=false; }); } },2000);
})();
