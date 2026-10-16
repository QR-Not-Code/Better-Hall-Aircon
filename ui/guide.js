/* Desktop + phone onboarding, including observable completion and manual checks. */
let connectRoute='capture',guideIndex=0;
const guideDone=new Set();
const captureGuide=[
 {id:'official',title:'手机：确认官方 App 能控制本房间',body:'打开 Hall Aircon，用自己的账号登录。尚未配对时，用 App 扫描墙上的房间二维码；如果已经配对，不要重复配对其他房间。先确认能正常读取状态并操作本人空调。',success:'官方 App 已登录、绑定正确房间，能够正常控制。',failure:'App 本身不能控制时，先处理账号、余额、绑定或设备离线问题，再继续。'},
 {id:'room',title:'电脑：保存房间设备编号',target:'room-card',auto:true,body:'在左侧第一张卡片，选择一种方式：① 粘贴墙上二维码的完整原文；② 点击“选择二维码图片并自动识别”，选择清晰照片。核对识别结果后，都要点击“保存编号”。',success:'出现“房间编号已保存”提示。这里是房间身份，不是手机 VPN 连接码。',failure:'图片识别失败就裁剪到二维码区域，或手动输入印在二维码下方的完整编号。'},
 {id:'network',title:'电脑 + 手机：先接入同一网络',target:'computer-card',body:'电脑插网线时：Windows Settings → Network & internet → Mobile hotspot，选择共享 Ethernet、通过 Wi-Fi 共享，设置名称和密码并开启。iPhone Settings → WLAN / Wi-Fi，连接这个热点。两台设备已在同一可互访局域网时，可沿用该网络。',success:'iPhone 已连接电脑热点或同一局域网，Safari 能正常上网。停止 Reqable 等其他 VPN。',failure:'电脑必须有支持热点的无线网卡。如果手机无法上网，先解决共享网络，再进行抓包。'},
 {id:'qr',title:'电脑：选择 IP，点击 ① 准备连接二维码',target:'prepare',auto:true,body:'在“手机能够访问的电脑 IPv4 地址”里选择热点网卡地址；Windows 热点通常是 192.168.137.1。若没有显示，先开启热点再点“刷新地址”。随后点击 ①。',success:'右侧出现 WireGuard 连接二维码，电脑地址对应手机连接的网络。',failure:'不要选手机自己的 IP。重新选择地址前，先停止正在运行的抓包。'},
 {id:'firewall',title:'电脑：点击 ② 配置防火墙',target:'firewall',auto:true,body:'点击 ②，在 Windows 管理员权限提示中选择“是 / Yes”。等待几秒，查看左侧底部的状态提示。只允许热点所在局域网访问本程序抓包端口，不需要关闭整个防火墙。',success:'状态提示出现“防火墙已配置”。',failure:'若显示配置失败，重新点击并允许管理员权限。未确认成功时不要继续排查手机证书。'},
 {id:'engine',title:'电脑：保留默认用途，点击 ③ 启动',target:'start-capture',auto:true,body:'第一次获取 Token，抓包用途保留“获取授权：核对成功后自动停止”，然后点击 ③ 启动并等待授权。以后录制温度、风速或模式才选“学习参数”。“停止抓包”用于手动结束。',success:'左侧状态显示“抓包引擎就绪”。',failure:'如果引擎退出，先检查端口占用；不要同时运行另一份抓包服务。'},
 {id:'wireguard',title:'手机：WireGuard 扫码并开启隧道',target:'wireguard-qr',auto:true,body:'App Store 安装免费的官方 WireGuard。打开后选择 ＋ → Create from QR code，用其内置扫码功能扫描电脑右侧的连接二维码，起名后点 Save。允许 VPN 配置，再开启隧道开关。不要用 Hall Aircon 或系统相机扫描这个码。',success:'电脑出现“近期已收到手机连接”；该检测只代表近期流量，证书仍需后续安装。',failure:'若连接后无法上网，检查 Endpoint 是否是电脑热点地址、端口 51820，以及上一步防火墙是否成功。'},
 {id:'certificate',title:'手机：在 Safari 下载 mitmproxy 证书',body:'保持电脑抓包和手机 WireGuard 开启。Safari 地址栏输入完整的 http://mitm.it，出现证书页面后选择 iOS / Apple 下载，弹窗选择 Allow。页面提示 Profile Downloaded 后再打开系统设置。',success:'Safari 提示描述文件已下载，Settings 中能找到待安装的 mitmproxy 描述文件。',failure:'若看到“If you can see this, traffic is not going through mitmproxy”，先关闭再开启隧道，用新标签页访问 http://mitm.it/?setup=2，不要继续安装旧证书。'},
 {id:'trust',title:'手机：安装证书，再开启完全信任',body:'Settings → General → VPN & Device Management → mitmproxy → Install，输入锁屏密码并确认。接着 Settings → General → About → Certificate Trust Settings，在 Enable Full Trust for Root Certificates 下开启本次 mitmproxy 证书，选择 Continue。',success:'mitmproxy 已安装，完全信任开关为绿色。',failure:'找不到描述文件说明下载步骤未完成；不要用 Reqable 或 Stream 的证书代替。'},
 {id:'token',title:'手机刷新 App，电脑自动获取并验证 Token',auto:true,body:'完全退出并重新打开 Hall Aircon，进入空调页面刷新状态；必要时正常操作一次本人空调。电脑会提取授权，调用 /me 核对保存的房间编号。等待成功提示，不需要在请求列表中寻找或手动复制。',success:'弹出“Token 获取成功，空调已连接”，显示绑定房间和完整 Token；普通获取模式会自动停止抓包。',failure:'房间不匹配、授权被拒绝或 App 出现证书错误时，按左侧错误提示处理，不会直接进入控制。'},
 {id:'cleanup',title:'手机：关闭 WireGuard，电脑复制 Token',body:'电脑提示抓包已停止后，在手机 WireGuard 关闭刚才的隧道，否则手机可能无法联网。在电脑成功窗口，点击 Token 文本或“复制完整 Token”，会复制纯 Token，不带多余说明。',success:'手机恢复正常联网；电脑提示“Token 已复制到剪贴板”。临时证书可移除。',failure:'选择了学习参数模式时，先点击电脑“停止抓包”保存学习结果，再关闭手机隧道。'},
 {id:'panel',title:'电脑：进入面板，确认连接完成',body:'点击成功窗口的“进入空调控制面板”。点右上角“刷新状态”，查看电源、温度、摆风和更新时间。需要测试时再点击“开启 / 关闭空调”或摆风按钮，最后现场确认实际设备响应。',success:'状态查询成功、房间身份已核对；需要操作的按钮返回目标状态确认。',failure:'状态来自后端，不能据此推断压缩机功率。Token 失效后可重新获取，或切换“已有 Token”直接导入。'}
];
const directGuide=[
 {id:'direct-input',title:'粘贴已有的完整 Token',body:'在左侧输入框粘贴自己的 Token，可以带 Bearer 前缀。无需填写房间编号、选择 IP、安装 WireGuard 或配置证书。',success:'输入框里是完整 Token，前后没有引号或缺失片段。',failure:'Token 必须属于已经在官方 App 绑定空调的账号。'},
 {id:'token',title:'点击验证，自动识别绑定房间',target:'manual-save',auto:true,body:'点击“验证 Token 并连接空调”。程序读取该 Token 对应的 /me，取得设备编号并检查状态；只有验证成功才替换本机保存的授权。',success:'弹出成功提示，显示 Token 绑定的房间编号。',failure:'过期、未绑定、格式错误时会提示原因，不需要为此启动抓包；请先换用有效 Token。'},
 {id:'cleanup',title:'核对房间，查看并复制 Token',body:'在成功窗口核对绑定房间。点击 Token 文本或“复制完整 Token”即可复制。凭据仍加密保存在本机，退出显示窗口后不继续展示。',success:'房间正确，按需完成复制。该路径不会启动抓包。'},
 {id:'panel',title:'进入控制面板并刷新',body:'点击“进入空调控制面板”，然后点击“刷新状态”。看到设备参数和最新时间即完成。开关、摆风等操作由你按需点击，不会在登录时自动执行。',success:'设备身份校验通过，当前运行状态显示正常。'}
];
function setConnectRoute(route){
 connectRoute=route;guideIndex=0;
 document.querySelectorAll('[data-capture-only]').forEach(e=>e.classList.toggle('hidden',route==='direct'));
 document.getElementById('direct-token-card').classList.toggle('hidden',route!=='direct');
 document.getElementById('route-capture').classList.toggle('selected',route==='capture');
 document.getElementById('route-direct').classList.toggle('selected',route==='direct');
 document.getElementById('guide-intro').textContent=route==='direct'?'已有 Token 无需抓包，按下面四步直接连接。':'电脑和手机交替操作。逐步展开，每一步都列出位置、操作和完成标志。';
 renderGuide();
}
function guideComplete(id,advance=true){guideDone.add(id);const steps=connectRoute==='direct'?directGuide:captureGuide;if(advance&&steps[guideIndex]?.id===id&&guideIndex<steps.length-1)guideIndex++;renderGuide();}
function guideObserve(id){if(!guideDone.has(id))guideComplete(id);}
function renderGuide(){
 const steps=connectRoute==='direct'?directGuide:captureGuide;
 const content=document.getElementById('guide-content');if(!content)return;
 const phase=guideIndex<2?0:guideIndex<6?1:guideIndex<9?2:guideIndex===9?3:4;
 document.querySelectorAll('#capture-steps span').forEach((e,n)=>e.classList.toggle('current',n===phase));
 document.getElementById('guide-progress').textContent=steps.filter(s=>guideDone.has(s.id)).length+' / '+steps.length+' 已完成';
 content.innerHTML=steps.map((s,n)=>`<details class="guide-step ${guideDone.has(s.id)?'done':''}" ${n===guideIndex?'open':''}><summary data-step="${n}"><span class="guide-number">${guideDone.has(s.id)?'✓':String(n+1).padStart(2,'0')}</span><b>${s.title}</b></summary><div class="guide-body"><p>${s.body}</p><div class="guide-success"><b>完成标志</b> ${s.success}</div>${s.failure?`<p class="guide-failure">卡住时：${s.failure}</p>`:''}<div class="guide-actions">${s.target?`<button class="text-btn" data-locate="${s.target}">定位对应控件 ↗</button>`:''}${s.auto&&!guideDone.has(s.id)?'<span class="caption">等待程序检测完成</span>':`<button class="btn secondary" data-complete="${s.id}">${guideDone.has(s.id)?'查看下一步 →':'我已完成，下一步 →'}</button>`}</div></div></details>`).join('');
 content.querySelectorAll('[data-step]').forEach(b=>b.onclick=e=>{e.preventDefault();guideIndex=Number(b.dataset.step);renderGuide();});
 content.querySelectorAll('[data-complete]').forEach(b=>b.onclick=()=>guideComplete(b.dataset.complete));
 content.querySelectorAll('[data-locate]').forEach(b=>b.onclick=()=>{const target=document.getElementById(b.dataset.locate);if(!target)return;target.scrollIntoView({behavior:'smooth',block:'center'});target.classList.add('guide-highlight');setTimeout(()=>target.classList.remove('guide-highlight'),2000);});
}
document.getElementById('route-capture').onclick=()=>setConnectRoute('capture');
document.getElementById('route-direct').onclick=()=>setConnectRoute('direct');
