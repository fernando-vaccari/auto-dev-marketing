/* Funções reais do Estúdio completo. Nenhum token é lido de volta do servidor. */
(() => {
  const s=id=>document.getElementById('studio-'+id);
  const r=id=>document.getElementById('reels-'+id);
  const request=(path,options)=>api('/reels'+path,options);
  const statuses={queued:'Na fila',rendering:'Gerando',ready:'Pronto',failed:'Falhou',cancelled:'Cancelado',awaiting_render:'Aguardando geração',awaiting_approval:'Aguardando aprovação',processing:'Processando na Meta',waiting:'Aguardando processamento',published:'Publicado',simulated:'Simulado',review_required:'Conferência manual necessária',recording:'Gravando',imported:'Importado'};
  let tab='create',config,initialized=false,refreshing=false,active=false,captureId=null,cutReview=null;
  let savedSchedules=[],instagram={mode:'demo'},variation=0;
  const split=value=>value.split(',').map(v=>v.trim()).filter(Boolean);
  const when=value=>new Date(value).toLocaleString('pt-BR',{timeZone:'America/Sao_Paulo'});
  const action=async(button,fn)=>{button.disabled=true;try{await fn();}catch(error){toast(error.message,true);}finally{button.disabled=false;}};
  const on=(id,fn)=>s(id).addEventListener('click',event=>{event.preventDefault();action(s(id),fn);});
  function openTab(name){
    tab=name;document.getElementById('view-reels').dataset.studioTab=name;
    document.querySelectorAll('[data-studio-tab]').forEach(button=>button.classList.toggle('active',button.dataset.studioTab===name));
    document.querySelectorAll('[data-studio-panel]').forEach(panel=>{panel.hidden=panel.dataset.studioPanel!==name;});
    s('create-area').hidden=!['create','library'].includes(name);
    if(name!=='create' && name!=='library')r('player').pause();
    refreshParts().catch(error=>toast(error.message,true));
  }
  function extra(body){
    return {...body,preset:s('preset').value,voice_id:s('voice-id').value,voice_speed:Number(s('speed').value),voice_volume:Number(s('volume').value),
      auto_shorten:s('shorten').checked,caption_style:s('caption-style').value,caption_font:s('caption-font').value,caption_size:Number(s('caption-size').value),
      caption_color:s('caption-color').value,caption_outline:Number(s('caption-outline').value),caption_shadow:Number(s('caption-shadow').value),caption_position:s('caption-position').value,
      caption_animation:s('caption-animation').checked,highlight_words:split(s('highlight').value),selection:s('selection').value,avoid_reuse:s('avoid-reuse').checked,
      cuts_override:cutReview?cutReview.map((cut,index)=>({...cut,source_start:Number(document.querySelector(`[data-cut-start="${index}"]`).value),duration:Number(document.querySelector(`[data-cut-duration="${index}"]`).value)})):null,
      script_style:s('script-style').value,game_name:s('game-name').value,confirmed_facts:s('facts').value.split('\n').map(v=>v.trim()).filter(Boolean),cta:s('cta').value,
      variation,music_volume:Number(s('music-volume').value),effect_id:r('effect').value||null};
  }
  window.AutoPostsStudio={extendPayload:extra,openTab};
  function invalidateCuts(){cutReview=null;s('cuts').replaceChildren();}
  document.querySelectorAll('[data-studio-tab]').forEach(button=>button.addEventListener('click',()=>openTab(button.dataset.studioTab)));
  r('create-form').addEventListener('input',event=>{if(!event.target.closest('#studio-cuts'))invalidateCuts();});
  r('plan').addEventListener('click',()=>{variation=(variation+1)%100000;});
  function applyPreset(name){
    s('preset').value=name;const preset=config.presets[name];
    r('zoom').value=String(Math.round(preset.zoom*100));s('music-volume').value=String(preset.music);
    s('caption-style').value='preset';invalidateCuts();
    toast(preset.name+' aplicado. Revise roteiro, enquadramento e trilha.');
  }
  s('preset').addEventListener('change',()=>applyPreset(s('preset').value));
  function applyCreation(body){
    const base={title:'title',duration:'duration',script:'script',tts:'voice',fit:'fit',music_id:'music'};
    for(const [key,id] of Object.entries(base))if(body[key]!==undefined && body[key]!==null)r(id).value=body[key];
    if(body.zoom!==undefined)r('zoom').value=String(Math.round(body.zoom*100));
    if(body.themes)r('themes').value=body.themes.join(', ');
    const fields={preset:'preset',voice_id:'voice-id',voice_speed:'speed',voice_volume:'volume',caption_style:'caption-style',caption_font:'caption-font',caption_size:'caption-size',caption_color:'caption-color',caption_outline:'caption-outline',caption_shadow:'caption-shadow',caption_position:'caption-position',selection:'selection',script_style:'script-style',game_name:'game-name',cta:'cta',music_volume:'music-volume'};
    for(const [key,id] of Object.entries(fields))if(body[key]!==undefined && body[key]!==null)s(id).value=body[key];
    for(const [key,id] of Object.entries({auto_shorten:'shorten',caption_animation:'caption-animation',avoid_reuse:'avoid-reuse'}))if(body[key]!==undefined)s(id).checked=body[key];
    if(body.confirmed_facts)s('facts').value=body.confirmed_facts.join('\n');
    if(body.highlight_words)s('highlight').value=body.highlight_words.join(', ');
    if(body.asset_ids)window.AutoPostsReels.setSelected(body.asset_ids);
    invalidateCuts();
  }
  const limitLabels={reels_upload_mb:['Limite por vídeo (MiB)',1,2048],reels_music_mb:['Limite por áudio (MiB)',1,256],reels_storage_mb:['Armazenamento do Estúdio (MiB)',256,65536],reels_min_free_mb:['Reserva livre de disco (MiB)',0,16384],reels_threads:['Threads por render',1,8],reels_queue_limit:['Jobs ativos e pendentes',1,10],reels_timeout_seconds:['Tempo máximo do job (segundos)',30,3600],reels_file_limit_mb:['Limite por arquivo gerado (MiB)',32,2048]};
  async function load(){
    const [prefs,obs,ig]=await Promise.all([request('/preferences'),request('/capture/config'),request('/instagram/config')]);
    instagram=ig;s('publishing-notice').textContent=ig.mode==='live' ? `Instagram Reels em modo real · ${ig.enabled?'envio habilitado, sujeito às aprovações':'envio desativado'}. A publicação de imagens mantém sua própria configuração.` : 'Instagram Reels em demonstração. Aprovações e regras simulam o envio sem chamar a Meta.';
    if(!initialized){
      const chosen=s('preset').value;s('preset').replaceChildren();
      for(const [id,preset] of Object.entries(config.presets))s('preset').append(new Option(preset.name,id));
      s('preset').value=chosen||'legacy';
      const cards=[];
      for(const [id,preset] of Object.entries(config.presets)){
        if(id==='legacy')continue;
        const card=node('article','studio-preset');card.append(node('h3','',preset.name),node('p','',`Cortes de até ${preset.cut}s · ${preset.transition==='dissolve'?'dissolve suave':'fade leve'} · zoom de ${Math.round(preset.zoom*100)}%`));
        const button=node('button','secondary','Usar este preset');button.type='button';button.addEventListener('click',()=>{applyPreset(id);openTab('create');});card.append(button);cards.push(card);
      }
      s('presets').replaceChildren(...cards);
      s('obs-port').value=obs.port;
      s('instagram-account').value=ig.account_id;s('instagram-app').value=ig.app_id;s('instagram-version').value=ig.api_version;
      s('instagram-mode').value=ig.mode;s('instagram-enabled').checked=ig.enabled;s('instagram-business').checked=ig.business_login_confirmed;s('instagram-permissions').checked=ig.permissions_confirmed;
      for(const [key,[label,min,max]] of Object.entries(limitLabels)){
        const field=node('label','',label);const input=node('input');input.type='number';input.min=min;input.max=max;input.value=prefs.limits[key];input.dataset.limit=key;field.append(input);s('limits').append(field);
      }
      if(prefs.studio)applyCreation(prefs.studio);
      initialized=true;
    }
    await refreshParts();
  }
  window.addEventListener('reels-loaded',event=>{config=event.detail;load().catch(error=>toast(error.message,true));});
  window.addEventListener('workspace-view',event=>{active=event.detail==='reels';if(!active){r('preview-player').pause();s('preview-player').pause();}});
  async function waitJob(identifier,statusId){
    const deadline=Date.now()+960000;
    while(Date.now()<deadline){
      const job=await request('/jobs/'+identifier);
      if(statusId)s(statusId).textContent=`${statuses[job.status]||job.status} · ${job.progress}%`;
      if(job.status==='ready')return job;
      if(['failed','cancelled'].includes(job.status))throw new Error(job.error||'Job cancelado.');
      await new Promise(resolve=>setTimeout(resolve,1000));
    }
    throw new Error('A consulta excedeu o tempo limite. Confira o histórico.');
  }
  const voiceControl=()=>{s('voice-id').disabled=r('voice').value!=='kokoro';};
  r('voice').addEventListener('change',voiceControl);
  window.addEventListener('reels-loaded',voiceControl);
  on('preview',async()=>{
    const body=window.AutoPostsReels.payload();body.script=s('preview-text').value;body.cuts_override=null;body.asset_ids=[];body.title='Prévia de narração';
    const job=await request('/voice-preview',{method:'POST',body});await waitJob(job.id,'preview-status');
    s('preview-player').src=`/api/reels/jobs/${job.id}/audio`;s('preview-player').hidden=false;
    const texts=await request(`/jobs/${job.id}/texts`);s('preview-status').textContent='Prévia pronta. Texto utilizado: '+texts.script;
  });
  on('analyze',async()=>{
    const body=window.AutoPostsReels.payload();body.cuts_override=null;
    const job=await request('/analyze',{method:'POST',body});await window.AutoPostsReels.selectJob(job.id);
    await waitJob(job.id,'analysis-status');s('analysis-status').textContent='Análise técnica concluída. Agora você pode revisar os cortes por qualidade.';
  });
  on('review-cuts',async()=>{
    invalidateCuts();const plan=await request('/plan',{method:'POST',body:window.AutoPostsReels.payload()});
    cutReview=plan.cuts.map(cut=>({asset_id:cut.asset_id,source_start:cut.source_start,duration:cut.duration}));
    const assets=window.AutoPostsReels.assets();s('cuts').replaceChildren();
    cutReview.forEach((cut,index)=>{
      const row=node('div','studio-cuts-row');const heading=node('strong','',assets.find(a=>a.id===cut.asset_id)?.original_name||cut.asset_id);
      const player=node('video','studio-cut-player');player.controls=true;player.preload='metadata';player.muted=true;player.hidden=true;
      const preview=button('Ver trecho',async()=>{const start=Number(document.querySelector(`[data-cut-start="${index}"]`).value);const duration=Number(document.querySelector(`[data-cut-duration="${index}"]`).value);if(!Number.isFinite(start+duration)||start<0||duration<=0)throw new Error('Informe um intervalo válido.');player.hidden=false;player.onloadedmetadata=()=>{player.currentTime=Math.min(start,Math.max(0,player.duration-.1));};player.ontimeupdate=()=>{if(player.currentTime>=start+duration)player.pause();};player.src=`/api/reels/assets/${cut.asset_id}/preview#t=${start},${start+duration}`;await player.play();});heading.append(preview);row.append(heading);
      for(const [key,label] of [['source_start','Início (s)'],['duration','Duração (s)']]){
        const field=node('label','',label);const input=node('input');input.type='number';input.min=key==='duration'?'0.033':'0';input.step='0.001';input.value=cut[key].toFixed(3);
        input.dataset[key==='duration'?'cutDuration':'cutStart']=String(index);field.append(input);row.append(field);
      }
      row.append(player);s('cuts').append(row);
    });
    s('analysis-status').textContent=plan.warning||'Cortes preparados. Ajuste intervalos reais preservando a duração total.';
  });
  on('reset-cuts',async()=>{invalidateCuts();s('analysis-status').textContent='O motor selecionará os cortes ao gerar.';});
  s('obs-form').addEventListener('submit',event=>{event.preventDefault();action(event.submitter,async()=>{
    const body={port:Number(s('obs-port').value)};if(s('obs-password').value)body.password=s('obs-password').value;
    await request('/capture/config',{method:'PUT',body});s('obs-password').value='';toast('Conexão OBS salva; senha existente preservada quando vazia.');
  });});
  on('obs-check',async()=>{
    const result=await request('/capture/status');s('obs-status').textContent=`OBS ${result.version} conectado · ${result.record_directory_supported?(result.recording?'gravando':'pronto para captura assistida'):'atualize obs-websocket para v5.3+ com controle de diretório'}`;
    s('obs-scene').replaceChildren(...result.scenes.map(scene=>new Option(scene.sceneName,scene.sceneName)));
    s('obs-source').replaceChildren(...result.inputs.map(input=>new Option(input.inputName,input.inputName)));
    captureId=result.owned_capture;s('capture-stop').disabled=!captureId;s('capture-start').disabled=!result.record_directory_supported;
  });
  s('capture-form').addEventListener('submit',event=>{event.preventDefault();action(s('capture-start'),async()=>{
    const body={input_name:s('obs-source').value,scene_name:s('obs-scene').value,sequence:s('sequence').value,
      themes:split(s('capture-themes').value),duration:Number(s('capture-duration').value),lead_seconds:Number(s('capture-lead').value),directory:s('capture-directory').value,game_confirmed:s('game-confirmed').checked};
    const result=await request('/capture/start',{method:'POST',body});captureId=result.id;s('capture-stop').disabled=false;s('obs-status').textContent=result.instruction;await refreshParts();
  });});
  on('capture-stop',async()=>{if(!captureId)throw new Error('Consulte a conexão para identificar a gravação desta instância.');await request(`/capture/${captureId}/stop`,{method:'POST'});captureId=null;s('capture-stop').disabled=true;s('obs-status').textContent='Gravação encerrada e importada.';await window.AutoPostsReels.enter();});
  s('weekdays').addEventListener('change',()=>{s('schedule-days').value=[...s('weekdays').querySelectorAll('input[type=checkbox]:checked')].map(input=>input.value).join(',');});
  s('schedule-form').addEventListener('submit',event=>{event.preventDefault();action(event.submitter,async()=>{
    const body={name:s('schedule-name').value,enabled:s('schedule-enabled').checked,days:split(s('schedule-days').value).map(Number),times:split(s('schedule-times').value),timezone:'America/Sao_Paulo',quantity:Number(s('schedule-quantity').value),policy:s('schedule-policy').value,regenerate_script:s('schedule-script').checked,library_mode:s('schedule-library').value,auto_authorized:s('schedule-authorized').checked,template:window.AutoPostsReels.payload()};
    const id=s('schedule-id').value;await request('/schedules'+(id?'/'+id:''),{method:id?'PUT':'POST',body});toast('Regra salva.');await refreshParts();
  });});
  on('schedule-new',async()=>{s('schedule-id').value='';s('schedule-name').value='Reels do RPG';s('schedule-enabled').checked=false;s('schedule-authorized').checked=false;});
  function button(label,fn){const b=node('button','secondary',label);b.type='button';b.addEventListener('click',()=>action(b,fn));return b;}
  function drawSchedules(rows,history){
    savedSchedules=rows;s('schedules').replaceChildren();
    for(const row of rows){const c=row.config;const item=node('article','studio-history-row');item.append(node('strong','',c.name),node('p','',`${c.enabled?'Ativa':'Pausada'} · ${c.times.join(' / ')} · ${c.quantity} Reel(s) por horário · ${c.policy==='automatic'?'Automática autorizada':c.policy==='approval'?'Aguardar aprovação':'Manual'}`));
      item.append(button('Editar',async()=>{s('schedule-id').value=row.id;s('schedule-name').value=c.name;s('schedule-days').value=c.days.join(',');s('weekdays').querySelectorAll('input[type=checkbox]').forEach(input=>{input.checked=c.days.includes(Number(input.value));});s('schedule-times').value=c.times.join(',');s('schedule-quantity').value=c.quantity;s('schedule-policy').value=c.policy;s('schedule-script').checked=c.regenerate_script!==false;s('schedule-library').value=c.library_mode||'selected';s('schedule-enabled').checked=c.enabled;s('schedule-authorized').checked=c.auto_authorized;applyCreation(c.template);toast('Regra carregada. Edite e salve para aplicar.');}),
        button(c.enabled?'Pausar':'Ativar',async()=>{await request('/schedules/'+row.id,{method:'PUT',body:{...c,enabled:!c.enabled}});await refreshParts();}),
        button('Executar agora',async()=>{const result=await request(`/schedules/${row.id}/run`,{method:'POST'});await refreshParts();if(!result.job_id)throw new Error('O horário registrou uma falha. Confira o histórico.');toast('Reel adicionado à fila.');}),
        button('Excluir regra',async()=>{await request('/schedules/'+row.id,{method:'DELETE'});await refreshParts();}));s('schedules').append(item);
    }
    if(!rows.length)s('schedules').append(node('p','help','Nenhuma regra ativa ou salva. Os horários sugeridos começam desativados.'));
    s('schedule-history').replaceChildren(...history.map(row=>node('p','help',`${when(row.created_at)} · ${statuses[row.status]||row.status}${row.detail?' · '+row.detail:''}`)));
  }
  s('instagram-form').addEventListener('submit',event=>{event.preventDefault();action(event.submitter,async()=>{
    const body={mode:s('instagram-mode').value,account_id:s('instagram-account').value,app_id:s('instagram-app').value,api_version:s('instagram-version').value,
      enabled:s('instagram-enabled').checked,business_login_confirmed:s('instagram-business').checked,permissions_confirmed:s('instagram-permissions').checked,authorize_live:s('instagram-authorize').checked};
    if(s('instagram-token').value)body.token=s('instagram-token').value;
    await request('/instagram/config',{method:'PUT',body});s('instagram-token').value='';s('instagram-authorize').checked=false;await load();toast('Configuração salva. Nenhum envio é feito ao salvar.');
  });});
  on('instagram-check',async()=>{const result=await request('/instagram/check',{method:'POST'});s('instagram-status').textContent=`Conta verificada: ${result.username||result.id}. Publicação real ainda não foi testada.`;});
  on('delivery-register',async()=>{const identifier=s('delivery-job').value;if(!identifier)throw new Error('Escolha um Reel concluído.');await request(`/jobs/${identifier}/delivery`,{method:'POST'});await refreshParts();toast('Publicação preparada para revisão.');});
  on('delivery-approve',async()=>{if(!s('delivery-reviewed').checked)throw new Error('Assista ao Reel e confirme a revisão antes de aprovar.');const identifier=s('delivery-job').value;
    await request(`/jobs/${identifier}/approval`,{method:'POST',body:{approved:true,authorize_live:s('delivery-live').checked}});s('delivery-reviewed').checked=false;s('delivery-live').checked=false;await refreshParts();toast(instagram.mode==='demo'?'Simulação autorizada.':'Envio autorizado. Acompanhe o histórico.');});
  let overviewAuth=false;
  async function overview(){if(!overviewAuth||document.hidden)return;const summary=await request('/summary');s('overview-summary').textContent=`${summary.ready} Reel(s) pronto(s) · ${summary.queue} tarefa(s) na fila/em execução · ${summary.rules_enabled} regra(s) ativa(s) · ${summary.published} publicação(ões) confirmada(s) · ${summary.simulated} simulação(ões).`;}
  window.addEventListener('app-ready',event=>{overviewAuth=event.detail.auth_enabled;overview().catch(()=>{});});
  setInterval(()=>{if(state.view==='overview')overview().catch(()=>{});},15000);
  s('delivery-job').addEventListener('change',()=>{s('delivery-reviewed').checked=false;s('delivery-live').checked=false;});
  function drawDeliveries(rows){
    const old=s('delivery-job').value;const ready=window.AutoPostsReels.jobs().filter(job=>job.status==='ready'&&job.kind==='reel');
    s('delivery-job').replaceChildren(...ready.map(job=>new Option(job.config.title+' · '+job.id.slice(0,8),job.id)));
    if(ready.some(job=>job.id===old))s('delivery-job').value=old;
    s('deliveries').replaceChildren(...rows.map(row=>{const item=node('article','studio-history-row');item.append(node('strong','',`${row.job_id.slice(0,8)} · ${statuses[row.status]||row.status}`),node('p','',`${when(row.updated_at)}${row.media_id?' · ID Instagram '+row.media_id:''}${row.error?' · '+row.error:''}`));return item;}));
    if(!rows.length)s('deliveries').append(node('p','help','Nenhuma publicação de Reels preparada.'));
  }
  async function refreshParts(){
    if(!active||refreshing)return;refreshing=true;
    try{
      if(tab==='automation'){const [rows,history]=await Promise.all([request('/schedules'),request('/schedule-history')]);drawSchedules(rows,history);}
      if(tab==='instagram')drawDeliveries(await request('/deliveries'));
      if(tab==='capture'){
        const rows=await request('/capture/history');s('capture-history').replaceChildren(...rows.map(row=>node('p','help',`${when(row.created_at)} · ${row.config.sequence} · ${statuses[row.status]||row.status}${row.error?' · '+row.error:''}`)));
        if(captureId && rows.some(row=>row.id===captureId&&row.status!=='recording')){captureId=null;s('capture-stop').disabled=true;toast('Captura encerrada. Confira o histórico e a biblioteca.');}
      }
    }finally{refreshing=false;}
  }
  s('limits-form').addEventListener('submit',event=>{event.preventDefault();action(event.submitter,async()=>{
    const limits={};document.querySelectorAll('[data-limit]').forEach(input=>{limits[input.dataset.limit]=Number(input.value);});await request('/preferences',{method:'PUT',body:{limits}});await window.AutoPostsReels.enter();toast('Limites salvos.');
  });});
  on('save-defaults',async()=>{const studio=window.AutoPostsReels.payload();studio.cuts_override=null;await request('/preferences',{method:'PUT',body:{studio}});toast('Configurações de criação salvas como padrão.');});
  setInterval(()=>{if(active&&!document.hidden)refreshParts().catch(error=>toast(error.message,true));},5000);
})();
