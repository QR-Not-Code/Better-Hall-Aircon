let cloudDocument=null,cloudReport=null,cloudCheckVersion=0;
async function cloudAction(fn){$('cloud-error').textContent='';try{return await fn();}catch(error){$('cloud-error').textContent=error.message;return null;}}
function cloudData(){return {...cloudDocument,cloud_mode:$('cloud-mode').value,interval:Number($('cloud-interval').value),job_minutes:Number($('cloud-minutes').value)};}
async function checkCloud(){
 const version=++cloudCheckVersion;cloudReport=null;$('cloud-save').disabled=true;$('cloud-check-result').textContent='正在检查兼容性…';
 $('cloud-interval-row').classList.toggle('hidden',$('cloud-mode').value!=='resume');$('cloud-minutes-row').classList.toggle('hidden',$('cloud-mode').value!=='once');
 const report=await rpc('cloud_check',cloudData());if(version!==cloudCheckVersion)return;
 cloudReport=report;$('cloud-copy-connections').disabled=!report.connections.length;
 $('cloud-check-result').innerHTML=(report.errors.length?'<b>需要先处理：</b><ul>'+report.errors.map(error=>'<li>'+esc(error)+'</li>').join('')+'</ul>':'<b>兼容检查通过</b>')+'<ul>'+report.warnings.map(warning=>'<li>'+esc(warning)+'</li>').join('')+'</ul>'+(report.connections.length?'<p>需要配置的连接：'+report.connections.map(esc).join('、')+'</p>':'');
 $('cloud-save').disabled=report.errors.length>0;
}
$('export-cloud').onclick=()=>action(async()=>{cloudDocument={...documentData(),program:currentDocumentProgram(),trusted_code:$('trust-code').checked};$('cloud-dialog').showModal();await checkCloud();});
$('cloud-mode').onchange=()=>cloudAction(checkCloud);$('cloud-interval').onchange=()=>cloudAction(checkCloud);$('cloud-minutes').onchange=()=>cloudAction(checkCloud);$('cloud-recheck').onclick=()=>cloudAction(checkCloud);
$('cloud-close').onclick=()=>$('cloud-dialog').close();
$('cloud-save').onclick=()=>cloudAction(async()=>{if(!cloudReport||cloudReport.errors.length)throw new Error('请先通过兼容检查。');const result=await rpc('export_cloud',cloudData());if(!result.cancelled)$('cloud-error').textContent='已导出 ZIP。请按 CLOUD-README.md 上传并配置 Secrets；尚未部署或控制设备。';});
$('cloud-copy-token').onclick=()=>cloudAction(async()=>{await rpc('copy_token');$('cloud-error').textContent='已复制 Token，请填写 AIRCON_TOKEN Secret。';});
$('cloud-copy-room').onclick=()=>cloudAction(async()=>{await rpc('copy_cloud_room');$('cloud-error').textContent='已复制房间编号，用于 AIRCON_EXPECTED_ROOM Secret。';});
$('cloud-copy-key').onclick=()=>cloudAction(async()=>{await rpc('copy_cloud_state_key');$('cloud-error').textContent='已复制本机进度密钥。仅首次配置时填写；已有云端进度请保持原密钥。';});
$('cloud-copy-connections').onclick=()=>cloudAction(async()=>{if(!cloudReport?.connections.length)throw new Error('当前脚本没有需要复制的命名连接。');await rpc('copy_cloud_connections',{names:cloudReport.connections});$('cloud-error').textContent='已复制，请填写 AIRCON_CONNECTIONS_JSON Secret。';});
window.smokeCloud=async()=>{
 const saved=documentData();
 loadWorkspace({blocks:{languageVersion:0,blocks:[chain(B('ac_power',{VALUE:'1'}),B('wait_seconds',{}, {SECONDS:N(7200)}),B('ac_power',{VALUE:'0'}))]}});
 cloudDocument={...documentData(),program:currentDocumentProgram(),trusted_code:false};
 $('cloud-mode').value='resume';$('cloud-dialog').showModal();await checkCloud();
 const result={button:!!$('export-cloud').onclick,dialog:$('cloud-dialog').open,compatible:cloudReport?.errors.length===0,exportEnabled:!$('cloud-save').disabled,secretButtons:!!$('cloud-copy-token').onclick&&!!$('cloud-copy-key').onclick};
 const exported=await rpc('cloud_smoke_export',cloudData());result.bundleExported=exported.saved;
 openDocument(saved);return result;
};
