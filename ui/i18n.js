/* Local, offline translation catalogue. Never send user data to a translator. */
let currentLanguage='zh-CN';
const translationEntries=Object.entries(window.EN||{}).sort((a,b)=>b[0].length-a[0].length);
const translationPattern=new RegExp(translationEntries.filter(([key])=>key.length>1).map(([key])=>key.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')).join('|')||'(?!)','g');
function tr(value){
 if(currentLanguage!=='en'||typeof value!=='string')return value;
 const trimmed=value.trim();if(Object.hasOwn(window.EN,trimmed))return value.replace(trimmed,window.EN[trimmed]);
 return value.replace(translationPattern,key=>window.EN[key]);
}
const nativeConfirm=window.confirm.bind(window),nativePrompt=window.prompt.bind(window),nativeAlert=window.alert.bind(window);
window.confirm=message=>nativeConfirm(tr(message));
window.prompt=(message,value)=>nativePrompt(tr(message),value);
window.alert=message=>nativeAlert(tr(message));
const translatedNodes=new WeakMap(),translatedAttributes=new WeakMap();
const protectedText='script,style,textarea,input,pre,code,.blocklySvg,.blocklyToolbox,.blocklyDropDownDiv,.blocklyWidgetDiv,#logs,#token-preview,#token-result-room,#connection-list b,#script-library option:not([value=""]),#dashboard-scripts option:not([value=""])';
function translateNode(node){
 if(!node.parentElement||node.parentElement.closest(protectedText))return;
 let record=translatedNodes.get(node);if(!record||node.nodeValue!==record.rendered)record={source:node.nodeValue};
 record.rendered=currentLanguage==='en'?tr(record.source):record.source;
 if(node.nodeValue!==record.rendered)node.nodeValue=record.rendered;translatedNodes.set(node,record);
}
function translateDOM(root=document.body){
 if(root.nodeType===Node.TEXT_NODE){translateNode(root);return;}
 if(root.nodeType!==Node.ELEMENT_NODE)return;
 const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);let node;while(node=walker.nextNode())translateNode(node);
 for(const element of [root,...root.querySelectorAll('[placeholder],[title],[aria-label],[alt]')]){
  if(element.closest('pre,code,.blocklySvg,.blocklyToolbox,.blocklyWidgetDiv'))continue;
  const records=translatedAttributes.get(element)||{};
  for(const name of ['placeholder','title','aria-label','alt'])if(element.hasAttribute(name)){
   const value=element.getAttribute(name);let record=records[name];if(!record||value!==record.rendered)record={source:value};
   record.rendered=currentLanguage==='en'?tr(record.source):record.source;
   if(value!==record.rendered)element.setAttribute(name,record.rendered);records[name]=record;
  }
  translatedAttributes.set(element,records);
 }
}
let translationQueued=false;
const languageObserver=new MutationObserver(records=>{
 if(translationQueued||!records.some(r=>!(r.target.parentElement||r.target).closest?.(protectedText)))return;
 translationQueued=true;requestAnimationFrame(()=>{translationQueued=false;translateDOM();});
});
languageObserver.observe(document.body,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['placeholder','title','aria-label','alt']});
