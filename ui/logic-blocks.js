/* Visible branch clauses, alongside ready-made compound blocks. */
operation('xor_logic','异或 XOR %1 与 %2（恰好一个为真）',[val('A','Boolean'),val('B','Boolean')],210,'xor',{a:I('A'),b:I('B')});
operation('xnor_logic','同或 XNOR %1 与 %2（真假相同）',[val('A','Boolean'),val('B','Boolean')],210,'xnor',{a:I('A'),b:I('B')});
operation('nand_logic','与非 NAND %1 与 %2',[val('A','Boolean'),val('B','Boolean')],210,'nand',{a:I('A'),b:I('B')});
operation('nor_logic','或非 NOR %1 与 %2',[val('A','Boolean'),val('B','Boolean')],210,'nor',{a:I('A'),b:I('B')});
operation('all_logic','列表 %1 是否全部为真 all',[val('VALUE')],210,'all',{value:I('VALUE')});
operation('any_logic','列表 %1 是否至少一项为真 any',[val('VALUE')],210,'any',{value:I('VALUE')});
operation('select_value','如果 %1 取值 %2 否则取值 %3',[val('COND','Boolean'),val('YES'),val('NO')],210,'select',{condition:I('COND'),yes:I('YES'),no:I('NO')});
operation('in_value','%1 在 %2 中 in',[val('ITEM'),val('VALUE')],210,'membership',{item:I('ITEM'),value:I('VALUE'),negate:C(false)});
operation('not_in_value','%1 不在 %2 中 not in',[val('ITEM'),val('VALUE')],210,'membership',{item:I('ITEM'),value:I('VALUE'),negate:C(true)});
operation('null_value','空值 None / null',[],210,'literal',{value:C(null)});
operation('null_check','%1 是空值 None / null 吗',[val('VALUE')],210,'is_null',{value:I('VALUE')});
operation('type_check','%1 的类型是 %2',[val('VALUE'),drop('TYPE',[['数字','number'],['文本','text'],['布尔','boolean'],['列表','list'],['对象','object'],['空值','null']])],210,'type_is',{value:I('VALUE'),type:F('TYPE')});
operation('truthy_value','把 %1 转为布尔值 bool',[val('VALUE')],210,'truthy',{value:I('VALUE')});
operation('finite_check','%1 是有效有限数字吗',[val('VALUE')],210,'is_finite',{value:I('VALUE')});
operation('defined_check','变量 %1 已定义吗',[textField('NAME','变量名')],210,'var_defined',{name:F('NAME')});
operation('pass_statement','pass · 空操作（保留位置）',[],40,'pass',{},false);
operation('raise_error','raise · 抛出错误 %1',[val('VALUE')],40,'raise',{value:I('VALUE')},false);
operation('try_finally','尝试 try %1 最后执行 finally %2',[body('DO'),body('FINALLY')],40,'try_finally',{body:{body:'DO'},finally:{body:'FINALLY'},has_catch:C(false)},false);
operation('try_except_finally','尝试 try %1 发生错误 except %2 最后执行 finally %3',[body('DO'),body('CATCH'),body('FINALLY')],40,'try_finally',{body:{body:'DO'},catch:{body:'CATCH'},finally:{body:'FINALLY'},has_catch:C(true)},false);
operation('while_else','当 while %1 重复 %2 正常结束 else %3',[val('COND','Boolean'),body('DO'),body('ELSE')],40,'while',{condition:I('COND'),until:C(false),body:{body:'DO'},else:{body:'ELSE'}},false);
operation('repeat_else','重复 %1 次 执行 %2 正常结束 else %3',[val('COUNT','Number'),body('DO'),body('ELSE')],40,'repeat',{count:I('COUNT'),body:{body:'DO'},else:{body:'ELSE'}},false);
operation('foreach_else','遍历 %1 当前项 %2 执行 %3 正常结束 else %4',[val('VALUE'),textField('NAME','变量名'),body('DO'),body('ELSE')],40,'for_each',{value:I('VALUE'),name:F('NAME'),body:{body:'DO'},else:{body:'ELSE'}},false);
operation('range_for','for 变量 %1 从 %2 到 %3（不含）步长 %4 执行 %5 正常结束 else %6',[textField('NAME','变量名'),val('START','Number'),val('END','Number'),val('STEP','Number'),body('DO'),body('ELSE')],40,'range_for',{name:F('NAME'),start:I('START'),end:I('END'),step:I('STEP'),body:{body:'DO'},else:{body:'ELSE'}},false);
define('switch_value','多分支 switch 值 %1 分支 %2',[val('VALUE'),{type:'input_statement',name:'CASES',check:'SWITCH_CASE'}],210);
define('switch_case','匹配 case %1 执行 %2',[val('VALUE'),body('DO')],210,{previousStatement:'SWITCH_CASE',nextStatement:'SWITCH_CASE'});
define('switch_default','其他情况 default %1',[body('DO')],210,{previousStatement:'SWITCH_CASE',nextStatement:'SWITCH_CASE'});
function compileCases(first){const cases=[];let fallback=[],hasDefault=false;for(let b=first;b;b=b.getNextBlock()){if(!b.isEnabled())continue;if(hasDefault)throw new Error('default 必须是 switch 的最后一个分支，且只能出现一次。');if(b.type==='switch_case')cases.push({value:input(b,'VALUE'),body:compileSequence(b.getInputTargetBlock('DO')),id:b.id});else if(b.type==='switch_default'){fallback=compileSequence(b.getInputTargetBlock('DO'));hasDefault=true;}else throw new Error('switch 只能放 case/default 分支。');}return {cases,default:fallback};}
// Blockly needs Boolean output checks to render predicates as condition pieces.
for(const type of ['xor_logic','xnor_logic','nand_logic','nor_logic','all_logic','any_logic','in_value','not_in_value','null_check','type_check','truthy_value','finite_check','defined_check']){
 const init=Blockly.Blocks[type].init;Blockly.Blocks[type].init=function(){init.call(this);this.setOutput(true,'Boolean');};
}
const branches=category('分支 · if / elif / else',210,['if_start','elif_branch','else_branch','switch_value','switch_case','switch_default','select_value']);
branches.contents.splice(3,0,{kind:'block',type:'controls_if',extraState:{hasElse:true}},{kind:'block',type:'controls_if',extraState:{elseIfCount:1,hasElse:true}});
toolbox.contents.splice(1,0,branches);
const logicCategory=toolbox.contents.find(c=>c.name==='逻辑 · 条件');
logicCategory.name='逻辑 · 条件组合';
logicCategory.contents.push(...['xor_logic','xnor_logic','nand_logic','nor_logic','all_logic','any_logic','in_value','not_in_value','null_value','null_check','type_check','truthy_value','finite_check','defined_check'].map(type=>({kind:'block',type})));
const flowCategory=toolbox.contents.find(c=>c.name==='流程 · 循环与异常');
flowCategory.contents.unshift(...['break_loop','continue_loop','range_for','while_else','repeat_else','foreach_else'].map(type=>({kind:'block',type})));
flowCategory.contents=flowCategory.contents.filter((entry,index,all)=>all.findIndex(other=>other.type===entry.type)===index);
flowCategory.contents.push(...['pass_statement','raise_error','try_finally','try_except_finally'].map(type=>({kind:'block',type})));
Blockly.Blocks.break_loop.init=(function(init){return function(){init.call(this);this.setTooltip('等同 Python break：只退出包住它的最近一层循环，不停止整个脚本。循环被 break 时不执行该循环的 else。');};})(Blockly.Blocks.break_loop.init);
Blockly.Blocks.continue_loop.init=(function(init){return function(){init.call(this);this.setTooltip('等同 Python continue：跳过当前循环本轮剩余动作，从下一轮继续；不会结束外层循环。');};})(Blockly.Blocks.continue_loop.init);
function smokeCompileBlock(block){
 let root=block;
 const make=type=>{const child=workspace.newBlock(type);child.initSvg();child.render();return child;};
 if(['elif_branch','else_branch'].includes(block.type)){
  root=make('if_start');const truth=make('logic_boolean');root.getInput('COND').connection.connect(truth.outputConnection);root.nextConnection.connect(block.previousConnection);
 }else if(['switch_case','switch_default'].includes(block.type)){
  root=make('switch_value');const value=make('math_number');root.getInput('VALUE').connection.connect(value.outputConnection);root.getInput('CASES').connection.connect(block.previousConnection);
 }else if(['break_loop','continue_loop'].includes(block.type)){
  root=make('controls_repeat_ext');const count=make('math_number');root.getInput('TIMES').connection.connect(count.outputConnection);root.getInput('DO').connection.connect(block.previousConnection);
 }
 const program=root.outputConnection?[{op:'log',value:compileExpr(root)}]:compileSequence(root);
 root.dispose(false);return program;
}
window.smokeLogic=()=>{
 const saved=Blockly.serialization.workspaces.save(workspace),result={};
 try{
  const truth=value=>B('logic_boolean',{BOOL:value?'TRUE':'FALSE'}),message=text=>B('log_value',{}, {VALUE:T(text)});
  loadWorkspace({blocks:{languageVersion:0,blocks:[chain(B('if_start',{}, {COND:truth(false),DO:message('if')}),B('elif_branch',{}, {COND:truth(true),DO:message('elif')}),B('else_branch',{}, {DO:message('else')}))]}});
  result.branchChain=compileWorkspace()[0];
  loadWorkspace({blocks:{languageVersion:0,blocks:[B('switch_value',{}, {VALUE:N(2),CASES:chain(B('switch_case',{}, {VALUE:N(2),DO:message('case')}),B('switch_default',{}, {DO:message('default')}))})]}});
  result.switch=compileWorkspace()[0];
  loadWorkspace({blocks:{languageVersion:0,blocks:[B('else_branch')]}});
  try{compileWorkspace();result.orphanRejected=false;}catch(error){result.orphanRejected=error.message.includes('elif/else');}
  loadWorkspace({blocks:{languageVersion:0,blocks:[chain(B('if_start',{}, {COND:truth(false)}),B('else_branch'),B('elif_branch',{}, {COND:truth(true)}))]}});
  try{compileWorkspace();result.lateElifRejected=false;}catch(error){result.lateElifRejected=error.message.includes('elif/else');}
  loadWorkspace({blocks:{languageVersion:0,blocks:[B('switch_value',{}, {VALUE:N(0),CASES:chain(B('switch_default'),B('switch_case',{}, {VALUE:N(1)}))})]}});
  try{compileWorkspace();result.lateCaseRejected=false;}catch(error){result.lateCaseRejected=error.message.includes('default');}
  const block=workspace.newBlock('controls_if');block.loadExtraState({hasElse:true});result.compoundElse=!!block.getInput('ELSE');block.loadExtraState({elseIfCount:1,hasElse:true});result.compoundElif=!!block.getInput('IF1')&&!!block.getInput('ELSE');block.dispose(false);
  return result;
 }finally{loadWorkspace(saved);}
};
const logicHelp=document.createElement('article');logicHelp.className='card';logicHelp.innerHTML='<h2>分支、break 与 continue</h2><div class="help-copy"><p><b>分支：</b>左侧“分支 · if / elif / else”有展开好的复合块，也可顺序拼接 if → 多个 elif → else。只执行第一个成立分支；else 可省略。elif/else 必须紧接前一个分支。</p><p><b>break：</b>位于“流程 · 循环与异常”最前面，结束最近一层循环，继续执行循环后面的动作。</p><p><b>continue：</b>跳过最近一层循环当前这轮的剩余动作，从下一轮继续；次数循环仍会计数，不影响外层循环。</p><p><b>循环 else：</b>正常完成次数、列表耗尽或条件变假时执行；break、错误、停止及演示截断不执行。break/continue 在循环外会被运行前检查阻止。</p><p><b>switch：</b>拖入 switch，把 case/default 接进它的分支槽，case 内放动作。只执行首个匹配项，default 必须最后，不需要额外 break。</p><p><b>更多判断：</b>逻辑分类提供 XOR、XNOR、NAND、NOR、all/any、in/not in、类型、空值、变量存在判断。条件取值只计算被选中的输入。</p><p><b>异常与占位：</b>pass 不做操作；raise 可进入错误分支；finally 用于正常、错误或循环跳转后的收尾。手动停止与运行超时优先，不保证执行清理动作。</p></div>';document.getElementById('page-help').querySelector('.help-grid').prepend(logicHelp);
