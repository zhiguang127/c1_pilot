"""Inline offline human form. All work stays in the reviewer's browser."""
import json


def render_form(template):
    payload = json.dumps(template, ensure_ascii=True).replace("<", "\\u003c")
    return r"""
<style>
.annotation{border:2px solid #193b55;padding:1.5rem;margin-top:3rem}.annotation label{display:block;margin:.6rem 0}.annotation input[type=text],.annotation textarea,.annotation select{display:block;box-sizing:border-box;width:100%;padding:.5rem}.annotation textarea{min-height:80px}.annotation fieldset{margin:1rem 0;padding:1rem}.annotation .checks label{display:inline-block;margin-right:1rem}.annotation button{padding:.8rem 1.2rem;background:#193b55;color:white;border:0;cursor:pointer}.annotation small{color:#444}
</style>
<section class="annotation" id="annotation"><h2>独立人工标注表</h2>
<p>填写后可导出本案例 JSON。表单不向服务器发送内容；关闭前请导出。无唯一最优或缺信息均可提交。校验命令会再检查全部观测引用和逻辑一致性。</p>
<div id="items-form"></div><h3>明确适用候选的逐对比较</h3><p>先选择适用性，对应比较会自动出现。每对均需判断。</p><div id="pairs-form"></div>
<fieldset id="decision-form"><legend>整体判断</legend></fieldset>
<label><input id="human-attestation" type="checkbox"> 我确认这是本人独立完成的人工评审，未借用另一评审或 LLM 标签。</label>
<button id="export-annotation" type="button">导出本案例标注</button><p id="form-message" role="status"></p></section>
<script>
const P1_TEMPLATE = __TEMPLATE__;
const refs = P1_TEMPLATE.items.map(x => x.candidate_ref);
const missingCodes = {symptoms:'症状',diagnoses:'诊断',medications:'药物',goals:'目标',preferences:'偏好',age:'年龄',work_schedule:'工作安排',wear_time:'佩戴时间',measurement_quality:'测量质量',activity_intensity:'活动强度',posture:'姿态',sleep_experience:'主观睡眠',timezone:'时区',history:'历史',other:'其他（理由中解释）'};
const reasonCodes = {applicability_condition:'适用条件',observation_interpretation:'观测解释',measurement_uncertainty:'测量不确定性',missing_context:'背景缺失',priority_criterion:'优先标准',reasonable_tie:'合理并列',source_scope:'来源范围',other:'其他（理由中解释）'};
function selectField(parent, id, label, options) {
  const wrap=document.createElement('label');wrap.textContent=label;
  const select=document.createElement('select');select.id=id;
  select.add(new Option('请选择',''));
  Object.entries(options).forEach(([value,text])=>select.add(new Option(text,value)));
  wrap.append(select);parent.append(wrap);return select;
}
function checks(parent,id,label,options) {
  const box=document.createElement('div');box.className='checks';box.id=id;
  const title=document.createElement('p');title.textContent=label;box.append(title);
  Object.entries(options).forEach(([value,text])=>{const l=document.createElement('label');const c=document.createElement('input');c.type='checkbox';c.value=value;l.append(c,document.createTextNode(' '+text));box.append(l)});
  parent.append(box);
}
function evidenceFields(parent,prefix) {
  for (const [suffix,label,tag] of [['observations','观测引用（逗号分隔，如 d29.sleep_minutes）','input'],['conditions','知识条件引用（逗号分隔，如 C1.observable_conditions.0）','input'],['rationale','理由：具体观测如何对应条件；比较时解释标准','textarea']]) {
    const l=document.createElement('label');l.textContent=label;const el=document.createElement(tag);el.id=prefix+'-'+suffix;if(tag==='input')el.type='text';l.append(el);parent.append(l);
  }
  checks(parent,prefix+'-missing','缺失信息（没有则不选）',missingCodes);
}
function fieldset(parent,id,title) {const f=document.createElement('fieldset');f.id=id;const l=document.createElement('legend');l.textContent=title;f.append(l);parent.append(f);return f}
refs.forEach(ref=>{const f=fieldset(document.getElementById('items-form'),'item-'+ref,ref+' 适用性');selectField(f,ref+'-applicability','适用性',{applicable:'适用',not_applicable:'不适用',insufficient_information:'信息不足'}).addEventListener('change',refreshPairs);evidenceFields(f,ref)});
function refreshPairs() {
  const applicable=refs.filter(r=>document.getElementById(r+'-applicability').value==='applicable');
  const active=new Set();
  applicable.forEach((left,i)=>applicable.slice(i+1).forEach(right=>{
    const prefix='pair-'+left+'-'+right;active.add(prefix);let f=document.getElementById(prefix);
    if(!f){f=fieldset(document.getElementById('pairs-form'),prefix,left+' 与 '+right);f.dataset.left=left;f.dataset.right=right;
      selectField(f,prefix+'-relation','相对优先关系',{left_preferred:left+' 优先',right_preferred:right+' 优先',tie:'合理并列',incomparable:'不可比较',insufficient_information:'缺少信息'});evidenceFields(f,prefix)}
    f.hidden=false;
  }));
  Array.from(document.getElementById('pairs-form').children).forEach(f=>f.hidden=!active.has(f.id));
}
const decision=document.getElementById('decision-form');
selectField(decision,'decision-priority','优先关系是否明确',{clear:'可完整判断，且有严格优先',partial:'部分优先关系可判断',none:'没有严格优先（并列或不可比较）',insufficient_information:'没有明确优先且缺少信息',not_comparable:'不足两个明确适用候选'});
selectField(decision,'decision-top','最优集合',{unique_best:'唯一最优',tied_best:'并列最优',undetermined:'不可比较，无法确定最优集合',insufficient_information:'信息不足，无法确定最优集合',not_comparable:'不足两个明确适用候选'});
checks(decision,'decision-best','最优候选集合（未确定时不选）',Object.fromEntries(refs.map(r=>[r,r])));
evidenceFields(decision,'decision');checks(decision,'decision-reasons','判断依据类型（至少一项）',reasonCodes);
function selected(id){return Array.from(document.querySelectorAll('#'+id+' input:checked')).map(x=>x.value)}
function values(id){return document.getElementById(id).value.split(/[,，\n]/).map(x=>x.trim()).filter(Boolean)}
function getEvidence(prefix){return {observations:values(prefix+'-observations'),conditions:values(prefix+'-conditions'),rationale:document.getElementById(prefix+'-rationale').value.trim(),missing_information:selected(prefix+'-missing')}}
document.getElementById('export-annotation').addEventListener('click',()=>{
  const message=document.getElementById('form-message');
  if(!document.getElementById('human-attestation').checked){message.textContent='请确认独立人工评审声明。';return}
  const record=structuredClone(P1_TEMPLATE);record.status='complete';record.human_attestation=true;record.completed_at=new Date().toISOString();
  record.items=refs.map(ref=>({candidate_ref:ref,applicability:document.getElementById(ref+'-applicability').value,...getEvidence(ref)}));
  record.comparisons=Array.from(document.getElementById('pairs-form').children).filter(f=>!f.hidden).map(f=>({left:f.dataset.left,right:f.dataset.right,relation:document.getElementById(f.id+'-relation').value,...getEvidence(f.id)}));
  record.decision={priority:document.getElementById('decision-priority').value,top_outcome:document.getElementById('decision-top').value,best_set:selected('decision-best'),...getEvidence('decision'),reason_codes:selected('decision-reasons')};
  if(record.items.some(x=>!x.applicability||!x.rationale||!x.conditions.length)||record.comparisons.some(x=>!x.relation||!x.rationale||!x.conditions.length)||!record.decision.priority||!record.decision.top_outcome||!record.decision.rationale||!record.decision.conditions.length||!record.decision.reason_codes.length){message.textContent='还有未完成的判断、条件引用或理由。';return}
  const blob=new Blob([JSON.stringify(record,null,2)+'\n'],{type:'application/json'});const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download=record.reviewer_id+'-'+record.case_ref+'.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);message.textContent='已导出。请保留文件，交给协调人运行校验；表单未替代证据和逻辑核验。';
});
</script>
""".replace("__TEMPLATE__", payload)
