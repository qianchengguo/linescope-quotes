const $ = id => document.getElementById(id);
let current = null;
const labels = {BLOCKED:'发现矛盾 · 阻止通过',NEEDS_REVIEW:'待人工复核',CHECKS_PASSED:'限定检查通过'};
async function api(path, body) {
  const response = await fetch(path, body === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const result = await response.json();
  if (!response.ok) throw new Error(JSON.stringify(result));
  return result;
}
function resetResult() {
  for (const id of ['calculations','findings','anchors','record','source-preview']) $(id).replaceChildren();
  $('verdict').textContent='尚未核验'; $('verdict').className='badge'; $('download').hidden=true;
  $('message').textContent='候选已载入。点击核验可保存一份实际检查记录。';
}
async function loadScenario(scenario) {
  current=null; resetResult();
  const data = await api('/api/demo');
  if (scenario==='arithmetic') {
    data.document.pages[0].text=data.document.pages[0].text.replace('合计 4500.00','合计 4200.00');
    data.extraction.total={value:'4200.00',evidence:{page:1,quote:'合计 4200.00'}};
  }
  if (scenario==='crossrow') data.extraction.items[0].quantity={value:'2',evidence:{page:1,quote:'数量 2'}};
  $('source').value=data.document.pages[0].text;
  $('candidate').value=JSON.stringify(data.extraction,null,2);
  $('coverage').checked=false; $('pricing').checked=false;
}
function review() { return {coverage_confirmed:$('coverage').checked,simple_pricing_confirmed:$('pricing').checked,reviewer:$('reviewer').value,reason:$('reason').value}; }
function sourceDocument() { return {pages:[{number:1,text:$('source').value}]}; }
function highlight(record, anchor) {
  const text=record.document.pages.find(page=>page.number===anchor.page).text;
  const mark=document.createElement('mark'); mark.textContent=text.slice(anchor.start,anchor.end);
  $('source-preview').replaceChildren(document.createTextNode(text.slice(0,anchor.start)),mark,document.createTextNode(text.slice(anchor.end)));
}
function render(record) {
  current=record; resetResult();
  const report=record.report;
  $('verdict').textContent=labels[report.verdict];
  $('verdict').className='badge '+({BLOCKED:'blocked',NEEDS_REVIEW:'review',CHECKS_PASSED:'passed'}[report.verdict]);
  $('message').textContent='来源：'+(record.metadata.mode==='ollama'?'本地 Ollama 模型候选':'手工 / 模拟候选')+'。每次修订另存记录；来源文本发生变化时建立新记录。';
  for (const calc of report.calculations) {
    const div=document.createElement('div'); div.className='calculation';
    div.textContent=`${calc.path} ｜ 复算 ${calc.expected} · 原文 ${calc.actual} · 差额 ${calc.delta}`;
    $('calculations').append(div);
  }
  for (const finding of report.findings) {
    const div=document.createElement('div');div.className='finding '+finding.severity;
    const title=document.createElement('strong');title.textContent=finding.code+' · '+finding.path;
    const text=document.createElement('span');text.textContent=finding.message;
    div.append(title,text);$('findings').append(div);
  }
  for (const [path,anchor] of Object.entries(report.anchors)) {
    const button=document.createElement('button');button.className='anchor';button.textContent=path+' ↗';
    button.addEventListener('click',()=>highlight(record,anchor));$('anchors').append(button);
  }
  $('record').textContent=`记录 ${record.id} ｜ 父版本 ${record.parent_id||'无'} ｜ 文本 SHA-256 ${report.document_sha256}`;
  $('download').href='/api/runs/'+record.id+'/export';$('download').hidden=false;
}
async function perform(button, action) {
  button.disabled=true;
  try { await action(); } catch(error) {
    resetResult(); $('message').textContent='未生成通过结果：'+error.message;
  } finally {button.disabled=false;}
}
for (const id of ['normal','arithmetic','crossrow']) $(id).addEventListener('click',()=>perform($(id),()=>loadScenario(id)));
$('verify').addEventListener('click',()=>perform($('verify'),async()=>{
  const document=sourceDocument(), extraction=JSON.parse($('candidate').value);
  const sameSource=current && JSON.stringify(current.document)===JSON.stringify(document);
  render(await api(sameSource?'/api/runs/'+current.id+'/revisions':'/api/runs',sameSource?{extraction,review:review()}:{document,extraction,review:review()}));
}));
$('extract').addEventListener('click',()=>perform($('extract'),async()=>{
  const record=await api('/api/extract',{document:sourceDocument()});
  $('candidate').value=JSON.stringify(record.extraction,null,2);
  $('coverage').checked=false;$('pricing').checked=false;render(record);
}));
loadScenario('normal').catch(error=>{$('message').textContent=error.message;});
