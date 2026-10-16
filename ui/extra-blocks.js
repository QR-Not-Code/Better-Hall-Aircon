/* Single catalogue drives block definitions and JSON compilation. */
const extraSpecs={};
function operation(type,message,args,colour,op,properties={},isValue=true){
 const booleans=new Set(['boolean','not','is_empty','in_range','list_contains','stable','changed','debounce','edge','hysteresis','between_time','state_flag']);
 const numbers=new Set(['random_int','random_float','clamp','unary','aggregate','smooth','elapsed']);
 if(isValue)expression(type,message,args,colour,booleans.has(op)?'Boolean':numbers.has(op)?'Number':null);
 else define(type,message,args,colour);
 extraSpecs[type]={op,properties};
}
const F=n=>({field:n}), I=n=>({input:n}), C=value=>({constant:value});
function compileExtra(b){const spec=extraSpecs[b.type],node={op:spec.op,id:b.id};for(const [key,source] of Object.entries(spec.properties))node[key]=source.field?field(b,source.field):source.input?input(b,source.input):source.body?compileSequence(b.getInputTargetBlock(source.body)):source.constant;return node;}
const fieldChoices=[['任何字段','*'],['电源','power'],['摆风','flap'],['设定温度','setpoint'],['风速','fanstep'],['模式','mode'],['通信状态','comm_stat'],['当前温度','current_temperature']];
const sourceChoices=[['任何来源','*'],['疑似外部操作','suspected_external'],['与本程序指令匹配','local_correlated'],['温度/通信遥测','telemetry']];
operation('and_explicit','与 %1 并且 %2',[val('A','Boolean'),val('B','Boolean')],210,'boolean',{operator:C('AND'),a:I('A'),b:I('B')});
operation('or_explicit','或 %1 或者 %2',[val('A','Boolean'),val('B','Boolean')],210,'boolean',{operator:C('OR'),a:I('A'),b:I('B')});
operation('not_explicit','非 %1',[val('VALUE','Boolean')],210,'not',{value:I('VALUE')});
operation('is_empty','%1 为空吗',[val('VALUE')],210,'is_empty',{value:I('VALUE')});
operation('coalesce','%1 为 null 时使用 %2',[val('VALUE'),val('FALLBACK')],210,'coalesce',{value:I('VALUE'),fallback:I('FALLBACK')});
operation('random_int','随机整数 从 %1 到 %2',[val('A'),val('B')],160,'random_int',{a:I('A'),b:I('B')});
operation('random_float','随机小数（0 ≤ 值 < 1）',[],160,'random_float');
operation('clamp','限制 %1 在 %2 到 %3 之间',[val('VALUE'),val('MIN'),val('MAX')],160,'clamp',{value:I('VALUE'),min:I('MIN'),max:I('MAX')});
operation('unary','%1 %2',[drop('OP',[['绝对值','ABS'],['四舍五入','ROUND'],['向下取整','FLOOR'],['向上取整','CEIL'],['平方根','SQRT']]),val('VALUE')],160,'unary',{operator:F('OP'),value:I('VALUE')});
operation('aggregate','列表 %1 的 %2',[val('VALUE'),drop('OP',[['总和','SUM'],['最小值','MIN'],['最大值','MAX'],['平均值','MEAN'],['中位数','MEDIAN']])],160,'aggregate',{operator:F('OP'),value:I('VALUE')});
operation('list_empty','空列表',[],260,'list',{items:C([])});
operation('list_pair','列表 %1 和 %2',[val('A'),val('B')],260,'list_pair',{a:I('A'),b:I('B')});
operation('list_get','列表 %1 第 %2 项（从 0 开始）',[val('VALUE'),val('INDEX')],260,'list_get',{value:I('VALUE'),index:I('INDEX')});
operation('list_contains','列表 %1 含有 %2',[val('VALUE'),val('ITEM')],260,'list_contains',{value:I('VALUE'),item:I('ITEM')});
operation('list_append','向列表变量 %1 追加 %2',[textField('NAME','变量名'),val('VALUE')],260,'list_append',{name:F('NAME'),value:I('VALUE')},false);
operation('object_value','对象 字段 %1 值 %2',[val('KEY'),val('VALUE')],260,'object',{key_value:I('KEY'),value:I('VALUE')});
operation('json_parse','解析 JSON 文本 %1',[val('VALUE')],260,'json_parse',{value:I('VALUE')});
operation('json_stringify','转换为 JSON 文本 %1',[val('VALUE')],260,'json_stringify',{value:I('VALUE')});
operation('split','拆分文本 %1 分隔符 %2',[val('VALUE'),val('SEP')],160,'split',{value:I('VALUE'),separator:I('SEP')});
operation('replace','文本 %1 把 %2 替换为 %3',[val('VALUE'),val('OLD'),val('NEW')],160,'replace',{value:I('VALUE'),old:I('OLD'),new:I('NEW')});
operation('text_case','文本 %1 %2',[val('VALUE'),drop('OP',[['转大写','UPPER'],['转小写','LOWER'],['去除两端空白','TRIM']])],160,'text_case',{value:I('VALUE'),operator:F('OP')});
operation('change_var','变量 %1 增加 %2',[textField('NAME','变量名'),val('VALUE')],280,'change_var',{name:F('NAME'),value:I('VALUE')},false);
operation('memory_set','持久保存 %1 为 %2',[textField('NAME','存档键名'),val('VALUE')],280,'memory_set',{name:F('NAME'),value:I('VALUE')},false);
operation('memory_get','持久读取 %1 不存在时 %2',[textField('NAME','存档键名'),val('FALLBACK')],280,'memory',{name:F('NAME'),fallback:I('FALLBACK')});
operation('between_time','当前时刻在 %1 到 %2（含跨午夜）',[textField('START','00:00'),textField('END','23:59')],205,'between_time',{start:F('START'),end:F('END')});
operation('elapsed','脚本已运行秒数',[],205,'elapsed');
operation('changed','检测 %1 变化 来源 %2 目标 %3（*任意）',[drop('FIELD',fieldChoices),drop('SOURCE',sourceChoices),textField('TARGET','*')],15,'changed',{field:F('FIELD'),source:F('SOURCE'),target:F('TARGET')});
operation('events_value','读取 %1 的变化事件 来源 %2',[drop('FIELD',fieldChoices),drop('SOURCE',sourceChoices)],15,'events',{field:F('FIELD'),source:F('SOURCE')});
operation('stable','%1 的观察值已稳定 %2 秒',[drop('FIELD',fieldChoices.slice(1)),val('SECONDS')],15,'stable',{field:F('FIELD'),seconds:I('SECONDS')});
operation('debounce','条件 %1 持续成立 %2 秒',[val('VALUE'),val('SECONDS')],15,'debounce',{value:I('VALUE'),seconds:I('SECONDS')});
operation('edge','条件 %1 的 %2',[val('VALUE'),drop('DIRECTION',[['上升沿（假→真）','RISE'],['下降沿（真→假）','FALL'],['任一边沿','ANY']])],15,'edge',{value:I('VALUE'),direction:F('DIRECTION')});
operation('hysteresis','数值 %1 回差 下界 %2 上界 %3',[val('VALUE'),val('LOW'),val('HIGH')],15,'hysteresis',{value:I('VALUE'),low:I('LOW'),high:I('HIGH')});
operation('smooth','数值 %1 的最近 %2 次平均值',[val('VALUE'),val('SIZE')],15,'smooth',{value:I('VALUE'),size:I('SIZE')});
operation('cooldown','冷却名称 %1 间隔至少 %2 秒 执行 %3',[textField('KEY','冷却名称'),val('SECONDS'),body('DO')],15,'cooldown',{key:F('KEY'),seconds:I('SECONDS'),body:{body:'DO'}},false);
operation('assert_condition','要求 %1 否则报错 %2',[val('COND'),textField('MESSAGE','错误说明')],40,'assert',{condition:I('COND'),message:F('MESSAGE')},false);
operation('wait_event','等待 %1 变化 来源 %2 最多 %3 秒 保存到变量 %4 发生时 %5 超时时 %6',[drop('FIELD',fieldChoices),drop('SOURCE',sourceChoices),val('TIMEOUT'),textField('NAME','变量名'),body('DO'),body('ELSE')],15,'wait_event',{field:F('FIELD'),source:F('SOURCE'),timeout:I('TIMEOUT'),name:F('NAME'),body:{body:'DO'},else:{body:'ELSE'}},false);
operation('http_request','用户接口 %1 方法 %2 JSON 请求体 %3 返回路径 %4',[textField('CONN','连接名称'),drop('METHOD',['GET','POST','PUT','PATCH','DELETE','HEAD'].map(s=>[s,s])),val('BODY'),textField('PATH','')],190,'http_request',{connection:F('CONN'),method:F('METHOD'),body:I('BODY'),path:F('PATH')});
operation('random_choice','从列表 %1 随机选择一项',[val('VALUE')],160,'random_choice',{value:I('VALUE')});
operation('in_range','数值 %1 在 %2 到 %3 之间',[val('VALUE'),val('LOW'),val('HIGH')],210,'in_range',{value:I('VALUE'),low:I('LOW'),high:I('HIGH')});
operation('text_slice','文本 %1 截取从 %2 到 %3（不含末位）',[val('VALUE'),val('START'),val('END')],160,'text_slice',{value:I('VALUE'),start:I('START'),end:I('END')});
operation('keys','对象 %1 的全部字段名',[val('VALUE')],260,'keys',{value:I('VALUE')});
operation('object_get','对象 %1 的字段 %2 不存在时 %3',[val('VALUE'),val('KEY'),val('FALLBACK')],260,'object_get',{value:I('VALUE'),key_value:I('KEY'),fallback:I('FALLBACK')});
operation('object_set','对象变量 %1 的字段 %2 设为 %3',[textField('NAME','变量名'),val('KEY'),val('VALUE')],260,'object_set',{name:F('NAME'),key_value:I('KEY'),value:I('VALUE')},false);
operation('list_range','范围列表 从 %1 到 %2（不含） 步长 %3',[val('START'),val('END'),val('STEP')],260,'list_range',{start:I('START'),end:I('END'),step:I('STEP')});
operation('for_each','遍历列表 %1 当前项变量 %2 执行 %3',[val('VALUE'),textField('NAME','变量名'),body('DO')],40,'for_each',{value:I('VALUE'),name:F('NAME'),body:{body:'DO'}},false);
operation('var_delete','删除变量 %1',[textField('NAME','变量名')],280,'var_delete',{name:F('NAME')},false);
operation('memory_delete','删除持久存档键 %1',[textField('NAME','存档键名')],280,'memory_delete',{name:F('NAME')},false);
operation('timestamp_format','时间戳 %1 按 %2 格式显示',[val('VALUE'),textField('FORMAT','%Y-%m-%d %H:%M:%S')],205,'timestamp_format',{value:I('VALUE'),format:F('FORMAT')});
operation('power_flag','空调电源现在 %1',[drop('TARGET',[['已开启','1'],['已关闭','0']])],115,'state_flag',{field:C('power'),target:F('TARGET')});
operation('swing_flag','自动摆风现在 %1',[drop('TARGET',[['已开启','S'],['已关闭','N']])],115,'state_flag',{field:C('flap'),target:F('TARGET')});
operation('power_changed','检测电源变为 %1 来源 %2',[drop('TARGET',[['开启','1'],['关闭','0'],['任意状态','*']]),drop('SOURCE',sourceChoices)],15,'changed',{field:C('power'),target:F('TARGET'),source:F('SOURCE')});
operation('swing_changed','检测摆风变为 %1 来源 %2',[drop('TARGET',[['开启','S'],['关闭','N'],['任意状态','*']]),drop('SOURCE',sourceChoices)],15,'changed',{field:C('flap'),target:F('TARGET'),source:F('SOURCE')});
define('custom_code','用户自定义模块 %1 超时 %2 秒',[textField('NAME','模块名称'),{type:'field_number',name:'TIMEOUT',value:60,min:1,max:3600}],325);
expression('custom_value','用户自定义接口 %1 输入 %2',[textField('NAME','接口名称'),val('VALUE')],325);
for(const type of ['custom_code','custom_value']){
 const init=Blockly.Blocks[type].init;
 Blockly.Blocks[type].init=function(){init.call(this);this.customSource='result = inputs';this.setTooltip('选中积木后，点击编辑器上方“编辑选中模块代码”。代码在本机 Python 进程执行。');};
 Blockly.Blocks[type].saveExtraState=function(){return {source:this.customSource};};
 Blockly.Blocks[type].loadExtraState=function(state){this.customSource=state.source||'result = inputs';};
}
const compileBaseExpr=compileExpr;
compileExpr=function(b){if(b.type==='custom_value')return {op:'custom_value',source:b.customSource,value:input(b,'VALUE'),id:b.id};if(extraSpecs[b.type]){const node=compileExtra(b);if(node.op==='list_pair')return {op:'list',items:[node.a,node.b]};return node;}return compileBaseExpr(b);};
const category=(name,colour,types)=>({kind:'category',name,colour,contents:types.map(type=>({kind:'block',type}))});
toolbox.contents=[
 category('设备 · 控制与读取',115,['ac_power','ac_swing','ac_set','ac_refresh','ac_state','power_flag','swing_flag']),
 category('逻辑 · 条件',210,['controls_if','logic_compare','and_explicit','or_explicit','not_explicit','logic_boolean','is_empty','coalesce','in_range']),
 category('流程 · 循环与异常',40,['controls_repeat_ext','controls_whileUntil','for_each','forever','wait_seconds','wait_condition','once_day','try_catch','retry_block','assert_condition','break_loop','stop_program']),
 category('事件 · 抗干扰',15,['power_changed','swing_changed','changed','events_value','wait_event','stable','debounce','edge','hysteresis','smooth','cooldown']),
 category('变量 · 存档',280,['var_set','var_get','change_var','var_delete','memory_set','memory_get','memory_delete']),
 category('计算 · 随机',160,['math_number','math_arithmetic','math_modulo','unary','clamp','random_int','random_float','random_choice','aggregate']),
 category('文本 · 转换',160,['text','text_join','text_length','text_contains','split','replace','text_slice','text_case','to_number']),
 category('列表 · JSON',260,['list_empty','list_pair','list_range','list_get','list_contains','list_append','object_value','object_get','object_set','keys','json_value','json_parse','json_stringify']),
 category('时间 · 日历',205,['clock','between_time','elapsed','timestamp_format','network_time','calendar_events']),
 category('连接 · HTTP / MQTT',190,['http_value','http_request','mqtt_value','network_ok']),
 category('输出 · 日志与提示',280,['log_value','notify_value']),
 category('扩展 · 用户代码',325,['custom_code','custom_value'])
];
toolbox.contents.find(c=>c.name.startsWith('文本')).contents[0].fields={TEXT:'文本内容'};
