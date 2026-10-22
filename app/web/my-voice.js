/* Minha Voz: mídia privada, gravação por gesto explícito, síntese na fila existente. */
(() => {
  const q=id=>document.getElementById('my-voice-'+id);
  const request=(path,options)=>api('/reels/my-voice'+path,options);
  let uploaded=null,recorder=null,stream=null,recordTimer=null,localUrl=null,state=null,jobId=null,approvedProfile=null,loading=false,defaultApplied=false;
  const extend=window.AutoPostsStudio.extendPayload;
  window.AutoPostsStudio.extendPayload=body=>({...extend(body),clone_profile_id:body.tts==='my_voice'?(q('selection').value||null):null});
  function status(text){q('status').textContent=text;}
  function fileReady(file){
    if(file.size>20*1024*1024)throw new Error('A amostra deve ter até 20 MiB.');
    uploaded=file;if(localUrl)URL.revokeObjectURL(localUrl);localUrl=URL.createObjectURL(file);
    q('local-player').src=localUrl;q('local-player').hidden=false;status('Amostra preparada. Ouça e clique em Validar e salvar amostra.');
  }
  async function refresh(){
    while(loading)await new Promise(resolve=>setTimeout(resolve,25));loading=true;
    try{
      state=await request('');q('runtime').textContent=state.runtime.engine+' · '+(state.runtime.installed?'Motor OpenVoice instalado; a qualidade deve ser conferida na prévia.':state.runtime.reason);
      const current=q('selection').value;q('selection').replaceChildren(new Option('Selecione um perfil',''));q('profiles').replaceChildren();
      for(const profile of state.profiles){
        q('selection').append(new Option(profile.name,profile.id));
        const row=document.createElement('div');row.className='reels-job';const text=document.createElement('span');text.textContent=`${profile.name} · ${profile.duration.toFixed(1)} s`;
        const audio=document.createElement('audio');audio.controls=true;audio.preload='none';audio.src=`/api/reels/my-voice/${profile.id}/audio`;audio.setAttribute('aria-label','Amostra '+profile.name);
        const remove=document.createElement('button');remove.type='button';remove.className='secondary';remove.textContent='Excluir perfil';
        remove.onclick=()=>action(remove,async()=>{await request(`/${profile.id}?delete_exports=${q('delete-exports').checked}`,{method:'DELETE'});if(approvedProfile===profile.id){approvedProfile=null;q('preview-player').pause();q('preview-player').removeAttribute('src');q('preview-player').hidden=true;}await window.AutoPostsReels.enter();await refresh();status('Perfil, original e áudios derivados removidos.');});
        row.append(text,audio,remove);q('profiles').append(row);
      }
      if(state.profiles.some(p=>p.id===current))q('selection').value=current;
      else if(state.default_profile_id)q('selection').value=state.default_profile_id;
      q('preview').disabled=!state.runtime.installed||!state.profiles.length;
      if(!defaultApplied&&state.runtime.installed&&state.default_profile_id&&state.profiles.some(p=>p.id===state.default_profile_id)&&document.querySelector('#reels-voice option[value=my_voice]')){
        document.getElementById('reels-voice').value='my_voice';document.getElementById('reels-voice').dataset.chosen='true';defaultApplied=true;
      }
    }finally{loading=false;}
  }
  async function action(button,fn){button.disabled=true;try{await fn();}catch(error){status(error.message);toast(error.message,true);}finally{button.disabled=button===q('record')&&recorder?.state==='recording';}}
  q('file').addEventListener('change',()=>{try{if(q('file').files[0])fileReady(q('file').files[0]);}catch(error){status(error.message);}});
  q('record').onclick=()=>action(q('record'),async()=>{
    if(!q('consent').checked)throw new Error('Confirme a autorização antes de gravar.');
    if(!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder)throw new Error('Microfone indisponível. Use localhost/HTTPS ou importe WAV/MP3.');
    stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true},video:false});
    const type=['audio/webm;codecs=opus','audio/ogg;codecs=opus','audio/mp4'].find(value=>MediaRecorder.isTypeSupported(value));
    try{recorder=new MediaRecorder(stream,type?{mimeType:type}:undefined);}catch(error){stream.getTracks().forEach(track=>track.stop());stream=null;throw error;}
    const chunks=[];recorder.ondataavailable=event=>{if(event.data.size)chunks.push(event.data);};
    recorder.onstop=()=>{clearTimeout(recordTimer);stream?.getTracks().forEach(track=>track.stop());stream=null;q('record').disabled=false;q('stop').disabled=true;
      const mime=recorder.mimeType;const ext=mime.includes('ogg')?'ogg':mime.includes('mp4')?'m4a':'webm';fileReady(new File(chunks,'microfone.'+ext,{type:mime}));};
    recorder.start(1000);q('stop').disabled=false;status('Gravando. Fale de 6 a 60 segundos; encerramento automático em 60 s.');
    recordTimer=setTimeout(()=>{if(recorder.state!=='inactive')recorder.stop();},60000);
  });
  q('stop').onclick=()=>{if(recorder&&recorder.state!=='inactive')recorder.stop();};
  q('save').onclick=()=>action(q('save'),async()=>{
    if(!uploaded)throw new Error('Grave ou selecione uma amostra.');if(!q('consent').checked)throw new Error('Confirme a autorização de uso da voz.');
    q('progress').hidden=false;q('progress').value=0;
    const params=new URLSearchParams({filename:uploaded.name,name:q('name').value,consent:'true'});
    const profile=await new Promise((resolve,reject)=>{const xhr=new XMLHttpRequest();xhr.open('POST','/api/reels/my-voice?'+params);xhr.setRequestHeader('Content-Type','application/octet-stream');
      xhr.upload.onprogress=e=>{if(e.lengthComputable)q('progress').value=e.loaded/e.total*100;};xhr.onerror=()=>reject(new Error('Falha no upload.'));
      xhr.onload=()=>{let body;try{body=JSON.parse(xhr.responseText);}catch{body={detail:'Resposta inválida.'};}if(xhr.status>=200&&xhr.status<300)resolve(body);else reject(new Error(body.detail||'Amostra recusada.'));};xhr.send(uploaded);});
    uploaded=null;q('file').value='';q('local-player').pause();q('local-player').removeAttribute('src');q('local-player').hidden=true;if(localUrl){URL.revokeObjectURL(localUrl);localUrl=null;}
    await window.AutoPostsReels.enter();await refresh();q('selection').value=profile.id;status('Perfil salvo localmente. Gere uma prévia para avaliar a semelhança.');
  });
  q('text').addEventListener('input',()=>{approvedProfile=null;q('approved').checked=false;});
  q('selection').onchange=()=>{approvedProfile=null;q('approved').checked=false;};
  q('preview').onclick=()=>action(q('preview'),async()=>{
    if(!q('selection').value)throw new Error('Selecione um perfil.');approvedProfile=null;q('approved').checked=false;
    const profile=q('selection').value;
    const body={...window.AutoPostsReels.payload(),asset_ids:[],cuts_override:null,title:'Prévia Minha Voz',duration:30,script:q('text').value,tts:'my_voice',clone_profile_id:profile};
    const job=await api('/reels/voice-preview',{method:'POST',body});jobId=job.id;q('cancel').disabled=false;
    try{
      for(;;){const row=await api('/reels/jobs/'+job.id);q('preview-status').textContent=`${row.progress}% · ${row.status==='rendering'?'Gerando voz local':row.status==='queued'?'Na fila':row.status}`;
        if(row.status==='ready'){approvedProfile=profile;q('preview-player').src=`/api/reels/jobs/${job.id}/audio`;q('preview-player').hidden=false;q('preview-status').textContent='Prévia pronta. Ouça antes de aprovar.';break;}
        if(['failed','cancelled'].includes(row.status))throw new Error(row.error||'Prévia cancelada.');await new Promise(resolve=>setTimeout(resolve,1000));}
    }finally{q('cancel').disabled=true;jobId=null;}
  });
  q('cancel').onclick=()=>action(q('cancel'),async()=>{if(jobId)await api('/reels/jobs/'+jobId+'/cancel',{method:'POST'});});
  q('use').onclick=()=>action(q('use'),async()=>{if(approvedProfile!==q('selection').value||!q('approved').checked)throw new Error('Gere uma prévia deste perfil, ouça e marque sua aprovação.');
    await request('/default',{method:'PUT',body:{profile_id:approvedProfile}});await window.AutoPostsReels.enter();document.getElementById('reels-voice').value='my_voice';document.getElementById('reels-voice').dataset.chosen='true';status('Minha Voz será selecionada nos novos Reels.');});
  q('clear-default').onclick=()=>action(q('clear-default'),async()=>{await request('/default',{method:'PUT',body:{profile_id:null}});await window.AutoPostsReels.enter();document.getElementById('reels-voice').value='kokoro';status('Padrão Minha Voz desativado.');});
  window.addEventListener('reels-loaded',()=>refresh().catch(error=>status(error.message)));
  document.addEventListener('click',event=>{const target=event.target.closest('[data-studio-tab],[data-view],#logout');if(target&&target.dataset.studioTab!=='my-voice'&&recorder?.state==='recording')recorder.stop();});
  window.addEventListener('pagehide',()=>{clearTimeout(recordTimer);stream?.getTracks().forEach(track=>track.stop());if(localUrl)URL.revokeObjectURL(localUrl);});
})();
