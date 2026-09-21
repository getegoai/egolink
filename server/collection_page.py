"""Credential-free collection shell; private data is fetched with device binding."""

COLLECTION_SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Content-Security-Policy": "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' blob:; media-src 'self' blob:; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}

COLLECTION_HTML = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>EgoLink 采集</title><link rel="stylesheet" href="/collection.css"></head>
<body><main><header><p>EGO LINK · 工程采集机</p><h1>采集</h1>
<nav><a href="/guardian-location">家属定位</a><a href="/engineering">工程详情</a><a href="/dev">⚡ 开发者工作台</a></nav>
<p>检查设备实际采集与入库数据。采集机不作为正式安全保障设备。</p></header>
<form id="connect" autocomplete="off"><label>设备 ID<input id="device-id" required maxlength="128" autocomplete="off" spellcheck="false"></label>
<label>测试项目凭证<input id="project-token" type="password" required maxlength="512" autocomplete="off"></label>
<button type="submit">连接采集视图</button></form>
<div class="controls"><button id="refresh" disabled>刷新</button><button id="forget" disabled>清除本页凭证与数据</button>
<label><input id="automatic" type="checkbox">每 10 秒刷新</label></div>
<p id="status" role="status" aria-live="polite">输入绑定到本设备的测试凭证。凭证只保存在本页内存中。</p>
<section id="overview" hidden><h2>最近已知状态</h2><p id="contact"></p><p id="totals"></p><p id="identity"></p>
<p class="hint">设备断网后，其即时缓存量未知。补传时间与采集时间分别显示；上传旧记录不会刷新源的采集状态。</p></section>
<section id="research" hidden><h2>本次测试与标注</h2>
<p>用途：知情测试人员的传感器数据采集，供采样、网络与定位算法研究。</p><p id="capture-policy"></p>
<p class="hint">访问范围：绑定本设备的测试凭证。保留期限与删除流程尚未配置，交机前需由项目负责人确认。本页不发送硬件开始、停止或录音命令。</p>
<form id="annotate" autocomplete="off"><label>已有会话（可留空）<input id="annotation-session" maxlength="128" list="sessions"><datalist id="sessions"></datalist></label>
<label>场景<input id="annotation-scene" maxlength="160" placeholder="室内、室外、步行、乘车"></label>
<label>佩戴方式<input id="annotation-wearing" maxlength="160" placeholder="胸前、手腕、包内"></label>
<label>备注<input id="annotation-note" maxlength="1024"></label>
<details><summary>可选设备时钟参考（不自动同步）</summary><label>boot_count<input id="annotation-boot" inputmode="numeric"></label><label>单调时间 ns<input id="annotation-mono" inputmode="numeric"></label></details>
<button type="submit">保存场景标注</button></form><p id="annotation-status" role="status"></p><div id="annotations"></div></section>
<section id="sources" class="sources" aria-live="polite"></section>
<section id="history" hidden><h2>原始记录与导出</h2>
<div class="controls"><label>数据源<select id="source-filter"><option value="">所有来源</option><option>gnss</option><option>lte</option><option>imu</option><option>wifi</option><option>power</option><option>device</option><option>time_anchor</option><option>source_status</option><option>session</option><option>loss</option><option>delivery</option></select></label>
<label>会话<input id="session-filter" maxlength="128" autocomplete="off" placeholder="全部会话"></label>
<button id="history-load">查看第一分段</button><button id="history-next" disabled>下一分段</button>
<button id="export-first">导出原始 JSONL</button><button id="export-next" disabled>导出下一分段</button></div>
<p class="hint">每段最多 100 项或 2 MB，导出清单明确标记是否结束及下一游标。先导出原始帧，再导出独立的人工标注与接收记录；按源导出同时包含配置、时间锚点、源状态与丢失摘要。</p>
<p id="export-status"></p><div id="records"></div></section>
</main><script src="/collection.js" defer></script></body></html>"""

COLLECTION_CSS = """
:root{font-family:system-ui,-apple-system,'Segoe UI',sans-serif;color:#17332d;background:#f4f7f5;color-scheme:light}
*{box-sizing:border-box}body{margin:0}main{max-width:1160px;margin:auto;padding:28px 20px 60px}header{border-bottom:1px solid #cddbd3;margin-bottom:24px;padding-bottom:16px}h1{font-size:36px;margin:8px 0}h2{font-size:21px}nav{display:flex;gap:20px}a{color:#126444}form,.controls{display:flex;gap:12px;flex-wrap:wrap;align-items:end;margin:16px 0}label{display:flex;gap:6px;flex-direction:column;font-size:14px}input,select,button{font:inherit;border:1px solid #a6b9ac;border-radius:7px;padding:9px 11px;background:white}button{background:#155f46;color:white;cursor:pointer}button:disabled{opacity:.45;cursor:default}input[type=checkbox]{width:auto}.sources{display:grid;grid-template-columns:repeat(auto-fit,minmax(310px,1fr));gap:16px}.source,section#overview,section#history{background:white;border:1px solid #d6e1da;border-radius:12px;padding:18px;margin-bottom:16px}.source h2{margin-top:0}.hint,.meta{color:#5b6c62;font-size:13px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px;max-height:360px;overflow:auto;background:#f4f7f5;padding:12px}details{margin:10px 0}canvas{width:100%;height:180px;background:#f6f8f7}#status{padding:12px;background:#e8f0eb;border-radius:8px}#records>details{border-bottom:1px solid #d6e1da;padding-bottom:8px}@media(max-width:600px){main{padding:18px 12px}form{align-items:stretch;flex-direction:column}.sources{grid-template-columns:1fr}}
"""

COLLECTION_JS = r"""(() => {
  'use strict';
  const el = (id) => document.getElementById(id);
  const names = {gnss:'GNSS',lte:'LTE / Cell',imu:'IMU 六轴',wifi:'Wi-Fi',power:'电源',device:'设备运行',camera:'Camera',audio:'Audio'};
  let credential = null, generation = 0, busy = null, historyCursor = null, exportCursor = null, historyFilter = '', exportFilter = '', pendingAnnotation = null, ageLabels = [], exportBusy = false;
  const text = (tag, value, className) => { const n=document.createElement(tag); n.textContent=value; if(className)n.className=className; return n; };
  const age = (value, now=Date.now()) => { const t=Date.parse(value); return Number.isFinite(t) ? Math.max(0,Math.floor((now-t)/1000))+' 秒前' : '未知'; };
  const sourceTime = (record) => {const e=record.envelope; return e.timestamp_utc || `绝对时间未知 · boot ${e.boot_count} / ${(e.timestamp_monotonic_ns/1e9).toFixed(3)} s`;};
  const ageLabel = (node,prefix,timestamp,suffix='') => {ageLabels.push({node,prefix,timestamp,suffix});node.textContent=`${prefix}${timestamp} (${age(timestamp)})${suffix}`;return node;};
  function updateAges(){for(const {node,prefix,timestamp,suffix} of ageLabels)node.textContent=`${prefix}${timestamp} (${age(timestamp)})${suffix}`;}
  function clearView(){ageLabels=[];for(const id of ['overview','history','research'])el(id).hidden=true;for(const id of ['sources','records','annotations','sessions'])el(id).replaceChildren();for(const id of ['contact','totals','identity','capture-policy','annotation-status','export-status'])el(id).textContent='';for(const id of ['annotation-session','annotation-scene','annotation-wearing','annotation-note','annotation-boot','annotation-mono','session-filter'])el(id).value='';historyCursor=exportCursor=pendingAnnotation=null;historyFilter=exportFilter='';el('history-next').disabled=el('export-next').disabled=true;}
  function filters(){ const q=new URLSearchParams({page_size:'100'}); if(el('source-filter').value)q.set('source',el('source-filter').value); if(el('session-filter').value.trim())q.set('session_id',el('session-filter').value.trim()); return q.toString(); }
  async function api(suffix, json=true, body=null){
    if(!credential)throw new Error('请先连接');
    const selected=credential, rev=generation;
    const r=await fetch(`/api/v1/devices/${encodeURIComponent(selected.device)}/collection/${suffix}`,{method:body===null?'GET':'POST',body:body===null?undefined:JSON.stringify(body),headers:{Authorization:'Bearer '+selected.token,...(body===null?{}:{'Content-Type':'application/json'})},cache:'no-store',credentials:'omit',redirect:'error'});
    if(rev!==generation)throw new Error('连接已变更');
    if(!r.ok)throw new Error(r.status===401?'凭证无效':r.status===403?'凭证未绑定此设备':`请求失败 (${r.status})`);
    const value=await (json?r.json():r.text());
    if(rev!==generation)throw new Error('连接已变更');
    return value;
  }
  function rawDetails(record){ const d=document.createElement('details'); d.append(text('summary','查看原始观测 / 配置 / 缺失原因')); d.append(text('pre',JSON.stringify(record.envelope,null,2))); return d; }
  function imuPlot(record){
    const p=record.envelope.payload;
    if(record.preview.status!=='ok'||p.encoding!=='offset_us+six_i16le+base64-v1')return null;
    try{const bytes=Uint8Array.from(atob(p.samples_b64),c=>c.charCodeAt(0));if(bytes.length!==p.sample_count*16)return null;
      const view=new DataView(bytes.buffer),canvas=document.createElement('canvas');canvas.width=640;canvas.height=180;canvas.setAttribute('aria-label','六轴原始计数曲线；横轴为真实样本时间偏移');
      const ctx=canvas.getContext('2d');if(!ctx)return null;
      const first=view.getUint32(0,true),last=view.getUint32((p.sample_count-1)*16,true),colors=['#145b47','#247bac','#a27416','#993e6f','#634dc2','#ac493c'];
      colors.forEach((color,axis)=>{ctx.beginPath();ctx.strokeStyle=color;for(let i=0;i<p.sample_count;i++){const offset=view.getUint32(i*16,true),x=10+620*(offset-first)/Math.max(1,last-first),y=90-view.getInt16(i*16+4+axis*2,true)/32768*80;const gap=i>0&&Number.isFinite(p.requested_interval_us)&&offset-view.getUint32((i-1)*16,true)>1.5*p.requested_interval_us;if(i&&!gap)ctx.lineTo(x,y);else ctx.moveTo(x,y);}ctx.stroke();});return canvas;
    }catch(_){return null;}
  }
  function render(summary){
    el('overview').hidden=false;el('history').hidden=false;el('research').hidden=false;
    ageLabels=[];
    const contact=summary.last_contact;
    if(contact)ageLabel(el('contact'),'最后联系：',contact.received_at,` · 接口：${contact.claimed_actual_transport}（设备报告）`);else el('contact').textContent='尚无已鉴权的采集入库记录';
    const total=summary.sources.reduce((a,s)=>({records:a.records+s.records,bytes:a.bytes+s.bytes,samples:a.samples+s.samples}),{records:0,bytes:0,samples:0});
    el('totals').textContent=`已入库 ${total.records} 条 / ${total.bytes} 字节原始帧 / ${total.samples} 个已解析 IMU 样本 · 重传去重 ${summary.delivery_counts.duplicate||0} · 身份冲突 ${summary.delivery_counts.conflict||0}`;
    const latest=[...summary.sources].sort((a,b)=>b.latest.envelope.boot_count-a.latest.envelope.boot_count||b.latest.envelope.timestamp_monotonic_ns-a.latest.envelope.timestamp_monotonic_ns)[0];
    el('identity').textContent=latest?`设备 ${summary.device_id} · 固件 ${latest.latest.envelope.fw_version} · 会话 ${latest.latest.envelope.session_id||'未命名'} · 配置 ${latest.latest.envelope.config_id}`:`设备 ${summary.device_id}`;
    el('sources').replaceChildren();
    const bySource=new Map(summary.sources.map(s=>[s.source,s]));
    const session=bySource.get('session'),policy=session?session.latest.envelope.payload:{};
    const enabled=value=>value===true?'已启用':value===false?'关闭':'未上报';
    el('capture-policy').textContent=`设备报告的会话状态：${policy.state||'未上报'} · 图像：${enabled(policy.camera_enabled)} · 音频：${enabled(policy.audio_enabled)} · 本地停止：${policy.stop_method||'设备未上报，交机前需确认'}`;
    el('sessions').replaceChildren();for(const s of summary.sessions||[]){const option=document.createElement('option');option.value=s.session_id;el('sessions').append(option);}
    el('annotations').replaceChildren();for(const a of summary.recent_annotations||[])el('annotations').append(text('p',`${a.server_annotation_time} · ${a.session_id||'未指定会话'} · ${a.scene} / ${a.wearing} / ${a.note}（人工标注，非自动同步）`,'meta'));
    for(const [source,name] of Object.entries(names)){
      const card=text('article','', 'source');card.append(text('h2',name));const s=bySource.get(source),state=(summary.source_states||{})[source];
      if(state){const p=state.envelope.payload;card.append(text('p',`最近源状态：${p.state||state.envelope.status} · 启用：${p.enabled===true?'是':p.enabled===false?'否':'未知'}`));card.append(text('p',`源状态时间：${sourceTime(state)}`,'meta'));if(state.envelope.missing_reason)card.append(text('p',state.envelope.missing_reason));}
      if(!s){card.append(text('p',state?'尚无该源的采样记录。':'尚无上报；安装与启用情况未确认。'));el('sources').append(card);continue;}
      const e=s.latest.envelope;
      card.append(text('p',`状态：${e.status} · 解析：${s.latest.preview.status}`));
      card.append(text('p',`最近源事件：${sourceTime(s.latest)}`,'meta'));
      card.append(ageLabel(text('p','','meta'),'最后收到该源：',s.last_server_received_at));
      card.append(text('p',`${s.records} 条 / ${s.samples} 样本 / ${s.bytes} 字节 · no_fix ${s.no_fix} · 错误 ${s.errors}`));
      if(e.missing_reason)card.append(text('p',e.missing_reason));
      if(source==='gnss'){
        if(e.payload.phase)card.append(text('p',`运行阶段：${e.payload.phase==='session_start_cleanup'||e.payload.phase==='start_cleanup'?'启动时电源状态清理':e.payload.phase} (${e.payload.phase})`));
        if(e.status==='no_fix')card.append(text('p','已保存本次原始响应；本次读取未得到定位解。'));
        if(e.status==='stopped')card.append(text('p','已收到接收机停止记录；先前定位查询保留在历史与原始导出中。'));
      }
      if(source==='lte'&&e.status==='partial')card.append(text('p','本次仅取得部分 Cell 字段；未取得项与各条 AT 结果保留在原始记录中。'));
      if(source==='power'&&e.status==='unavailable')card.append(text('p','本次未提供可用的实测电源读数；空值保持未知。'));
      if(source==='device'||source==='power')card.append(text('pre',JSON.stringify(e.payload,null,2)));
      if(source==='imu'){card.append(text('p',`本块 ${e.payload.sample_count??'未知'} 个样本 · 读取错误 ${e.payload.read_errors??'未上报'} · 逾期 ${e.payload.missed_deadlines??'未上报'}`));const plot=imuPlot(s.latest);if(plot){card.append(plot);card.append(text('p','原始计数：加速度 XYZ / 陀螺 XYZ。超过配置间隔 1.5 倍的时间缺口断开显示；量程、换算与实际偏移见原始记录。','meta'));}}
      card.append(rawDetails(s.latest));el('sources').append(card);
    }
    for(const source of ['source_status','session','time_anchor','loss','delivery']){
      const s=bySource.get(source);if(!s)continue;const card=text('article','', 'source');card.append(text('h2',source));card.append(text('p',`最近事件：${sourceTime(s.latest)}`,'meta'));card.append(rawDetails(s.latest));el('sources').append(card);
    }
  }
  async function refresh(){if(busy===generation||!credential)return;const rev=generation;busy=rev;try{const data=await api('summary');if(data.device_id!==credential.device)throw new Error('响应设备身份不匹配');render(data);el('status').textContent='已刷新。显示各源最近已知状态，绝对时间未知的离线段保持未知。';}catch(e){if(rev===generation)el('status').textContent=e.message;}finally{if(busy===rev)busy=null;}}
  el('connect').addEventListener('submit',async e=>{e.preventDefault();generation++;credential={device:el('device-id').value.trim(),token:el('project-token').value.trim()};el('project-token').value='';clearView();el('refresh').disabled=el('forget').disabled=false;await refresh();});
  el('refresh').addEventListener('click',refresh);
  el('forget').addEventListener('click',()=>{generation++;credential=null;el('project-token').value=el('device-id').value='';clearView();el('refresh').disabled=el('forget').disabled=true;el('automatic').checked=false;el('status').textContent='本页凭证与数据已清除。设备采集和待传缓存不受影响。';});
  el('annotate').addEventListener('submit',async event=>{event.preventDefault();try{
    const nullableInt=id=>{const s=el(id).value.trim();if(!s)return null;if(!/^\d+$/.test(s)||!Number.isSafeInteger(Number(s)))throw new Error('设备时钟参考必须是安全范围内的非负整数');return Number(s);};
    const body={session_id:el('annotation-session').value.trim()||null,scene:el('annotation-scene').value.trim(),wearing:el('annotation-wearing').value.trim(),note:el('annotation-note').value.trim(),boot_count:nullableInt('annotation-boot'),timestamp_monotonic_ns:nullableInt('annotation-mono')};
    const key=JSON.stringify(body);if(!pendingAnnotation||pendingAnnotation.key!==key)pendingAnnotation={key,body:{annotation_id:'annotation-'+crypto.randomUUID(),...body}};
    const result=await api('annotations',true,pendingAnnotation.body);pendingAnnotation=null;
    el('annotation-status').textContent=`已保存：${result.annotation.server_annotation_time}。这是人工标注的服务器时间，不代表设备已同步。`;
    await refresh();
  }catch(error){el('annotation-status').textContent=error.message;}});
  async function history(next){try{const filter=filters();if(next&&filter!==historyFilter)throw new Error('筛选已改变，请查看第一分段');historyFilter=filter;const data=await api('records?'+filter+(next&&historyCursor?'&cursor='+encodeURIComponent(historyCursor):''));el('records').replaceChildren();data.records.sort((a,b)=>a.envelope.boot_count-b.envelope.boot_count||a.envelope.timestamp_monotonic_ns-b.envelope.timestamp_monotonic_ns).forEach(r=>{const d=document.createElement('details');d.append(text('summary',`${r.envelope.source} · ${sourceTime(r)} · ${r.envelope.status}`));d.append(text('p',`VPS 收到 ${r.server_received_at} · ${r.envelope.observation_id}`,'meta'));d.append(text('pre',JSON.stringify(r,null,2)));el('records').append(d);});historyCursor=data.page.next_cursor;el('history-next').disabled=data.page.exhausted;el('export-status').textContent=`本段 ${data.records.length} 条。${data.page.exhausted?'已到快照末尾。':'还有后续分段。'}`;}catch(e){el('export-status').textContent=e.message;}}
  function checkedExport(data){const rows=data.trimEnd().split('\n').map(line=>JSON.parse(line)),manifest=rows.shift();if(manifest.kind!=='collection_export_manifest'||manifest.device_id!==credential.device)throw new Error('导出清单设备身份不匹配');const counts={collection_record:0,operator_annotation:0,delivery_attempt:0};for(const row of rows){if(!Object.hasOwn(counts,row.kind))throw new Error('导出包含未知记录类型');counts[row.kind]++;}const page=manifest.page;if(counts.collection_record!==page.record_count||counts.operator_annotation!==(page.annotation_count||0)||counts.delivery_attempt!==(page.delivery_attempt_count||0))throw new Error('导出分段不完整：记录数与清单不符');if(typeof page.exhausted!=='boolean'||(page.exhausted? page.next_cursor!==null : typeof page.next_cursor!=='string'||!page.next_cursor))throw new Error('导出游标不完整');return manifest;}
  async function download(next){if(exportBusy)return;exportBusy=true;try{const filter=filters();if(next&&filter!==exportFilter)throw new Error('筛选已改变，请重新开始导出');exportFilter=filter;const data=await api('export.jsonl?'+filter+(next&&exportCursor?'&cursor='+encodeURIComponent(exportCursor):''),false);const manifest=checkedExport(data);const url=URL.createObjectURL(new Blob([data],{type:'application/x-ndjson'})),a=document.createElement('a');a.href=url;a.download=`egolink-${manifest.page.snapshot_max_id}-${manifest.page.record_count}-${Date.now()}.jsonl`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);exportCursor=manifest.page.next_cursor;el('export-next').disabled=manifest.page.exhausted;el('export-status').textContent=`已生成 ${manifest.page.record_count} 条原始记录、${manifest.page.annotation_count||0} 条人工标注、${manifest.page.delivery_attempt_count||0} 条接收记录的下载。${manifest.page.exhausted?'本次快照的全部分段已生成。请确认文件已保存。':'尚未完成，请继续导出下一分段；游标也保存在文件首行。'}`;}catch(e){el('export-status').textContent=e.message;}finally{exportBusy=false;}}
  el('history-load').addEventListener('click',()=>history(false));el('history-next').addEventListener('click',()=>history(true));el('export-first').addEventListener('click',()=>download(false));el('export-next').addEventListener('click',()=>download(true));
  setInterval(()=>{updateAges();if(credential&&el('automatic').checked&&!document.hidden)refresh();},10000);
})();
"""
