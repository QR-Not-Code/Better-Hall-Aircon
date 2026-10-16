/* Blockly is bundled locally. Programs compile to an explicit JSON tree, never eval. */
const statement = {previousStatement:null,nextStatement:null};
function textField(name,text){return {type:'field_input',name,text};}
function drop(name,options){return {type:'field_dropdown',name,options};}
function val(name,check){return {type:'input_value',name,...(check?{check}:{})};}
function body(name){return {type:'input_statement',name};}
function define(type,message,args,colour,extra={}){Blockly.defineBlocksWithJsonArray([{type,message0:message,args0:args,colour,tooltip:message.replace(/%\d+/g,''),...(Object.hasOwn(extra,'output')?{}:statement),...extra}]);}
function expression(type,message,args,colour,output=null){define(type,message,args,colour,{output});}
define('ac_power','空调电源 %1',[drop('VALUE',[['开启','1'],['关闭','0']])],115);
define('ac_swing','自动摆风 %1',[drop('VALUE',[['开启','S'],['关闭','N']])],115);
define('ac_set','设置空调 %1 为 %2',[drop('FIELD',[['设定温度','setpoint'],['风速','fanstep'],['模式','mode']]),val('VALUE')],115);
define('ac_refresh','刷新空调状态',[],115);
expression('ac_state','空调的 %1',[drop('FIELD',[['电源（1开0关）','power'],['当前温度','current_temperature'],['设定温度','setpoint'],['摆风（S开N关）','flap'],['风速代码','fanstep'],['模式代码','mode'],['通信状态','comm_stat']])],115);
define('wait_seconds','停顿 %1 秒',[val('SECONDS','Number')],40);
define('forever','持续循环 %1',[body('DO')],40);
define('try_catch','尝试执行 %1 发生错误时 %2',[body('DO'),body('CATCH')],40);
define('retry_block','失败重试最多 %1 次 间隔 %2 秒 %3',[{type:'field_number',name:'ATTEMPTS',value:3,min:1,max:10},{type:'field_number',name:'INTERVAL',value:10,min:5,max:300},body('DO')],40);
define('wait_condition','等待条件成立 %1 每 %2 秒检查一次',[val('COND','Boolean'),{type:'field_number',name:'INTERVAL',value:30,min:5,max:3600}],40);
define('once_day','当天只执行一次（名称 %1） %2',[textField('KEY','名称'),body('DO')],40);
define('stop_program','停止本脚本',[],40);
define('break_loop','break · 结束当前循环',[],40);
define('continue_loop','continue · 跳过本轮，继续下一轮',[],40);
define('if_start','如果 if %1 则 %2',[val('COND','Boolean'),body('DO')],210);
define('elif_branch','否则如果 elif %1 则 %2',[val('COND','Boolean'),body('DO')],210);
define('else_branch','否则 else %1',[body('DO')],210);
define('var_set','设置变量 %1 为 %2',[textField('NAME','变量名'),val('VALUE')],280);
expression('var_get','变量 %1',[textField('NAME','变量名')],280);
define('log_value','记录到日志 %1',[val('VALUE')],280);
define('notify_value','在界面显示提示 %1',[val('VALUE')],280);
expression('json_value','从 %1 读取 JSON 路径 %2',[val('VALUE'),textField('PATH','字段路径')],280);
expression('to_number','转换为数字 %1',[val('VALUE')],280,'Number');
expression('text_contains','文字 %1 包含 %2',[val('TEXT'),val('PART')],160,'Boolean');
expression('clock','当前 %1',[drop('FIELD',[['小时（0–23）','hour'],['分钟（0–59）','minute'],['星期（周一1至周日7）','weekday'],['时刻（HH:MM）','hhmm'],['日期（YYYY-MM-DD）','date'],['Unix 时间戳','timestamp']])],205);
expression('http_value','HTTP 连接 %1 的 JSON 路径 %2',[textField('CONN','连接名称'),textField('PATH','字段路径')],190);
expression('mqtt_value','MQTT 连接 %1 的 JSON 路径 %2',[textField('CONN','连接名称'),textField('PATH','字段路径')],190);
expression('network_ok','HTTP 连接 %1 能访问吗',[textField('CONN','连接名称')],190,'Boolean');
expression('network_time','HTTP 连接 %1 的网络时间戳',[textField('CONN','连接名称')],205,'Number');
expression('calendar_events','日历 %1 未来 %2 小时的事件 标题包含 %3',[textField('CONN','连接名称'),{type:'field_number',name:'HOURS',value:24,min:1,max:720},textField('KEYWORD','')],205);

const numberBlock=n=>({kind:'block',type:'math_number',fields:{NUM:n}});
const textBlock=s=>({kind:'block',type:'text',fields:{TEXT:s}});
const toolbox={kind:'categoryToolbox',contents:[
 {kind:'category',name:'空调动作',colour:115,contents:['ac_power','ac_swing','ac_set','ac_refresh','ac_state'].map(type=>({kind:'block',type}))},
 {kind:'category',name:'逻辑判断',colour:210,contents:['controls_if','logic_compare','logic_operation','logic_negate','logic_boolean'].map(type=>({kind:'block',type}))},
 {kind:'category',name:'循环与流程',colour:40,contents:[{kind:'block',type:'controls_repeat_ext',inputs:{TIMES:{shadow:{type:'math_number',fields:{NUM:3}}}}},{kind:'block',type:'controls_whileUntil'},{kind:'block',type:'forever'},{kind:'block',type:'wait_seconds',inputs:{SECONDS:{shadow:{type:'math_number',fields:{NUM:60}}}}},...['wait_condition','once_day','try_catch','retry_block','break_loop','stop_program'].map(type=>({kind:'block',type}))]},
 {kind:'category',name:'变量与数据',colour:280,contents:['var_set','var_get','json_value','to_number','log_value','notify_value'].map(type=>({kind:'block',type}))},
 {kind:'category',name:'数字与文字',colour:160,contents:[numberBlock(25),...['math_arithmetic','math_modulo'].map(type=>({kind:'block',type})),textBlock('文本内容'),...['text_join','text_length','text_contains'].map(type=>({kind:'block',type}))]},
 {kind:'category',name:'时间与日历',colour:205,contents:['clock','network_time','calendar_events'].map(type=>({kind:'block',type}))},
 {kind:'category',name:'传感器与网络',colour:190,contents:['http_value','mqtt_value','network_ok'].map(type=>({kind:'block',type}))},
]};

function input(b,name){const c=b.getInputTargetBlock(name);if(!c)throw new Error('有一个输入槽还没有连接积木：'+b.type);return compileExpr(c);}
function field(b,name){return b.getFieldValue(name);}
function compileExpr(b){
 const type=b.type, f=n=>field(b,n), i=n=>input(b,n);
 if(type==='math_number')return {op:'literal',value:Number(f('NUM'))};
 if(type==='text')return {op:'literal',value:f('TEXT')};
 if(type==='logic_boolean')return {op:'literal',value:f('BOOL')==='TRUE'};
 if(type==='logic_compare'||type==='logic_operation'||type==='math_arithmetic')return {op:{logic_compare:'compare',logic_operation:'boolean',math_arithmetic:'math'}[type],operator:f('OP'),a:i('A'),b:i('B')};
 if(type==='logic_negate')return {op:'not',value:i('BOOL')};
 if(type==='math_modulo')return {op:'math',operator:'MODULO',a:i('DIVIDEND'),b:i('DIVISOR')};
 if(type==='text_join')return {op:'join',items:Array.from({length:b.itemCount_},(_,n)=>i('ADD'+n))};
 if(type==='text_length')return {op:'length',value:i('VALUE')};
 if(type==='text_contains')return {op:'contains',text:i('TEXT'),part:i('PART')};
 if(type==='var_get')return {op:'var',name:f('NAME')};
 if(type==='json_value')return {op:'path',value:i('VALUE'),path:f('PATH')};
 if(type==='to_number')return {op:'number',value:i('VALUE')};
 if(type==='ac_state')return {op:'state',field:f('FIELD')};
 if(type==='clock')return {op:'time',field:f('FIELD')};
 if(type==='http_value'||type==='mqtt_value')return {op:type==='http_value'?'http':'mqtt',connection:f('CONN'),path:f('PATH')};
 if(type==='network_ok'||type==='network_time')return {op:type==='network_ok'?'network':'net_time',connection:f('CONN')};
 if(type==='calendar_events')return {op:'calendar',connection:f('CONN'),hours:Number(f('HOURS')),keyword:f('KEYWORD')};
 throw new Error('不支持的数值积木：'+type);
}
function compileSequence(first){
 const result=[];
 for(let b=first;b;b=b.getNextBlock()){
  if(!b.isEnabled())continue;
  const f=n=>field(b,n),i=n=>input(b,n),body=n=>compileSequence(b.getInputTargetBlock(n));
  let node;const t=b.type;
  if(t==='elif_branch'||t==='else_branch'){
   const previous=result[result.length-1];
   if(!previous||previous.op!=='if'||previous.has_else)throw new Error('elif/else 必须紧接 if 或 elif；else 只能有一个并放在最后。');
   if(t==='elif_branch')previous.branches.push({condition:i('COND'),body:body('DO'),id:b.id});
   else{previous.else=body('DO');previous.has_else=true;}
   continue;
  }
  if(t==='ac_power'||t==='ac_swing')node={op:'control',field:t==='ac_power'?'power':'flap',value:{op:'literal',value:f('VALUE')}};
  else if(t==='ac_set')node={op:'control',field:f('FIELD'),value:i('VALUE')};
  else if(t==='ac_refresh')node={op:'refresh'};
  else if(t==='wait_seconds')node={op:'wait',seconds:i('SECONDS')};
  else if(t==='var_set')node={op:'set',name:f('NAME'),value:i('VALUE')};
  else if(t==='log_value')node={op:'log',value:i('VALUE')};
  else if(t==='notify_value')node={op:'notify',value:i('VALUE')};
  else if(t==='controls_repeat_ext')node={op:'repeat',count:i('TIMES'),body:body('DO')};
  else if(t==='controls_whileUntil')node={op:'while',until:f('MODE')==='UNTIL',condition:i('BOOL'),body:body('DO')};
  else if(t==='forever')node={op:'forever',body:body('DO')};
  else if(t==='once_day')node={op:'once_day',key:f('KEY'),body:body('DO')};
  else if(t==='wait_condition')node={op:'wait_until',condition:i('COND'),interval:Number(f('INTERVAL'))};
  else if(t==='try_catch')node={op:'try',body:body('DO'),catch:body('CATCH')};
  else if(t==='retry_block')node={op:'retry',attempts:Number(f('ATTEMPTS')),interval:Number(f('INTERVAL')),body:body('DO')};
  else if(t==='stop_program'||t==='break_loop'||t==='continue_loop')node={op:t==='stop_program'?'stop':t==='break_loop'?'break':'continue'};
  else if(t==='if_start')node={op:'if',branches:[{condition:i('COND'),body:body('DO')}],else:[],has_else:false};
  else if(t==='switch_value')node={op:'switch',value:i('VALUE'),...compileCases(b.getInputTargetBlock('CASES'))};
  else if(t==='switch_case'||t==='switch_default')throw new Error('case/default 只能接在 switch 的分支槽中。');
  else if(t==='custom_code')node={op:'custom_code',source:b.customSource,timeout:Number(f('TIMEOUT'))};
  else if(extraSpecs[t])node=compileExtra(b);
  else if(t==='controls_if'){
   const branches=[];let n=0;
   while(b.getInput('IF'+n)){branches.push({condition:i('IF'+n),body:body('DO'+n)});n++;}
   node={op:'if',branches,else:body('ELSE'),has_else:!!b.getInput('ELSE')};
  } else throw new Error('不支持的动作积木：'+t);
  result.push({...node,id:b.id});
 }
 return result;
}
function compileWorkspace(){
 const tops=workspace.getTopBlocks(true).filter(b=>b.isEnabled());
 const loose=tops.filter(b=>b.outputConnection);
 if(loose.length)throw new Error('画布上有未接入流程的数值积木，请连接或删除。');
 if(tops.length>1)throw new Error('请把动作连接为一条流程，避免执行顺序不明确。');
 if(!tops.length)throw new Error('请先拖入动作积木。');
 return compileSequence(tops[0]);
}

const B=(type,fields={},inputs={},next=null,extraState=null)=>{if(next&&!next.type){extraState=next;next=null;}return {type,fields,...(Object.keys(inputs).length?{inputs:Object.fromEntries(Object.entries(inputs).map(([k,v])=>[k,{block:v}]))}:{}),...(next?{next:{block:next}}:{}),...(extraState?{extraState}:{})};};
const N=n=>B('math_number',{NUM:n}),T=s=>B('text',{TEXT:s}),V=s=>B('var_get',{NAME:s}),S=s=>B('ac_state',{FIELD:s});
const chain=(...blocks)=>{for(let n=0;n<blocks.length-1;n++)blocks[n].next={block:blocks[n+1]};return blocks[0];};
const compare=(op,a,b)=>B('logic_compare',{OP:op},{A:a,B:b});
function templateBlocks(){return {blocks:{languageVersion:0,blocks:[]}};}
