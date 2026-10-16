/* Rebuild labels from originals, retaining field values, code, IDs and layout. */
const originalToolbox=JSON.parse(JSON.stringify(toolbox));
const originalJSONInit=Blockly.Block.prototype.jsonInit;
Blockly.Block.prototype.jsonInit=function(definition){
 if(currentLanguage!=='en')return originalJSONInit.call(this,definition);
 const localized={...definition};
 for(const [key,value] of Object.entries(localized)){
  if(typeof value==='string'&&(/^(message\d+|tooltip|helpUrl)$/.test(key)))localized[key]=tr(value);
  if(/^args\d+$/.test(key)&&Array.isArray(value))localized[key]=value.map(argument=>{
   const translated={...argument};
   if(typeof translated.text==='string')translated.text=tr(translated.text);
   if(Array.isArray(translated.options))translated.options=translated.options.map(([label,id])=>[typeof label==='string'?tr(label):label,id]);
   return translated;
  });
 }
 return originalJSONInit.call(this,localized);
};
for(const definition of Object.values(Blockly.Blocks)){
 const initialize=definition.init;if(!initialize)continue;
 definition.init=function(){
  initialize.call(this);
  if(currentLanguage!=='en')return;
  for(const input of this.inputList)for(const field of input.fieldRow){
   if(field instanceof Blockly.FieldDropdown){const choices=field.getOptions(false);if(Array.isArray(choices)&&choices.every(x=>typeof x[0]==='string'))field.setOptions(choices.map(([label,value])=>[tr(label),value]));}
   else if(field instanceof Blockly.FieldLabel||field instanceof Blockly.FieldTextInput)field.setValue(tr(field.getValue()));
  }
  if(typeof this.tooltip==='string')this.setTooltip(tr(this.tooltip));
 };
}
function applyLanguage(language){
 language=language==='en'?'en':'zh-CN';
 document.getElementById('language-select').value=language;
 document.documentElement.lang=language;
 if(language===currentLanguage){translateDOM();return;}
 // Flush the custom-module editor into the block before serializing it.
 if(typeof syncCustomCode==='function')syncCustomCode();
 const snapshot=workspace?Blockly.serialization.workspaces.save(workspace):null;
 const scale=workspace?.scale,selected=Blockly.getSelected()?.id;
 currentLanguage=language;
 Blockly.setLocale(language==='en'?window.blocklyEnglish:window.blocklyChinese);
 const localized=JSON.parse(JSON.stringify(originalToolbox));
 for(const category of localized.contents)category.name=tr(category.name);
 if(workspace){
  Blockly.Events.disable();
  try{workspace.clear();workspace.updateToolbox(localized);if(snapshot)Blockly.serialization.workspaces.load(snapshot,workspace);if(scale)workspace.setScale(scale);}
  finally{Blockly.Events.enable();}
  if(typeof customTarget!=='undefined'&&customTarget)customTarget=workspace.getBlockById(customTarget.id);
  if(selected)workspace.getBlockById(selected)?.select();
  Blockly.svgResize(workspace);
 }
 translateDOM();
}
document.getElementById('language-select').onchange=()=>action(async()=>{
 const selector=document.getElementById('language-select'),before=currentLanguage;
 try{const result=await rpc('language',{value:selector.value});applyLanguage(result.language);}catch(error){selector.value=before;throw error;}
});
document.getElementById('check-updates').onclick=()=>action(()=>rpc('check_updates'));
const previousApplySettings=applySettings;
applySettings=function(value){previousApplySettings(value);if(value.version)document.getElementById('app-version').textContent='v'+value.version;if(value.language)applyLanguage(value.language);};
window.smokeLanguage=async()=>{
 const original=currentLanguage,saved=documentData(),trusted=$('trust-code').checked;
 customTarget=null;editorMode='blocks';$('script-name').value='我的未保存脚本';$('code-source').value='result = "不要翻译我的代码"';
 loadWorkspace({blocks:{languageVersion:0,blocks:[{type:'var_set',fields:{NAME:'用户的变量'},inputs:{VALUE:{block:{type:'text',fields:{TEXT:'用户自己的文字'}}}},next:{block:{type:'custom_code',extraState:{source:'result = "自定义内容"'}}}}]}});
 const documentBefore=JSON.stringify(documentData()),programBefore=JSON.stringify(currentDocumentProgram());
 applyLanguage('en');await new Promise(resolve=>setTimeout(resolve,120));
 const result={navigation:document.querySelector('[data-page="dashboard"] span').textContent==='Aircon control',
  guide:!/[\u3400-\u9fff]/.test(document.getElementById('guide-content').textContent),
  categories:workspace.getToolbox().getToolboxItems().every(item=>!/[\u3400-\u9fff]/.test(item.getName())),
  unchanged:JSON.stringify(documentData())===documentBefore,
  compiledUnchanged:JSON.stringify(currentDocumentProgram())===programBefore};
 const block=workspace.newBlock('ac_power');block.initSvg();block.render();result.block=block.toString().includes('Aircon power');result.blockText=block.toString();block.dispose(false);
 applyLanguage('zh-CN');await new Promise(resolve=>setTimeout(resolve,80));result.chinese=document.querySelector('[data-page="dashboard"] span').textContent==='空调控制';
 applyLanguage(original);openDocument(saved);$('trust-code').checked=trusted;return result;
};
