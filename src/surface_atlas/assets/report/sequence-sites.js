/* Exact canonical intervals. Each target owns persistent partner/interval state. */
(() => {
  'use strict';
  function selection(record, start, end, partnerIDs) {
    if (!Number.isInteger(start) || !Number.isInteger(end) || start < 1 || start > end || end > record.length) throw new Error('Choose a valid one-based inclusive interval.');
    const mappings = record.mappings.filter(m => m.canonical_position >= start && m.canonical_position <= end);
    const partners = record.partners.filter(p => partnerIDs.includes(p.partner_id));
    const exact = record.sequence.slice(start - 1, end);
    const chains = [...new Set(mappings.map(m => m.chain))].join(',') || 'unresolved';
    const context = {target_id:record.target_id, accession:record.accession, isoform:record.isoform,
      source_id:record.source_id, canonical_range:{start,end}, numbering:'canonical one-based inclusive; coordinates author',
      coordinate_model:record.coordinate_model, canonical_sequence_sha256:record.sequence_sha256,
      canonical_sequence:record.sequence,
      coordinates:record.coordinates, mappings, partners, sequence:exact,
      sequence_scope:'selected canonical interval, one-based inclusive; canonical_sequence_sha256 hashes the complete canonical_sequence ASCII bytes',
      unresolved_positions:Array.from({length:end-start+1},(_,i)=>i+start).filter(p=>!mappings.some(m=>m.canonical_position===p))};
    const header = `${record.accession}|isoform=${record.isoform || 'canonical'}|target=${record.target_id}|canonical=${start}-${end}|author_chains=${chains}|model=1|numbering=canonical_1based_inclusive`;
    const fasta = `>${header}\n${exact.match(/.{1,60}/g).join('\n')}\n`;
    const prompt = 'Inspect this exact sequence/site selection in Codex. Verify the source hashes before opening files. Use only the explicit author-residue mappings; do not align, renumber, fill unresolved gaps, or infer exposure. Preserve partner identities and the selected partners.\n\n' + JSON.stringify(context,null,2) + '\n\nExact FASTA:\n' + fasta;
    const layers = mappings.length ? [{object_name:'coordinates', label:`${record.accession} canonical ${start}–${end}`, color:'#247562', representation:'stick',opacity:1,
      selection:{}, verified_residues:mappings.map(m=>({...m, amino_acid:record.sequence[m.canonical_position-1]}))}] : [];
    for (const p of partners) layers.push({object_name:'coordinates',label:`${p.label} (${p.accession}; ${p.partner_id})`,color:'#386ba8',representation:'stick',opacity:1,selection:{chain:p.chain,hetflag:false}});
    const scene = {sources:[{href:record.coordinates.path,sha256:record.coordinates.sha256,format:'pdb',object_name:'coordinates',state:1}],layers};
    return {context,fasta,prompt,scene,mapped:mappings.length};
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = {selection};
  if (typeof document === 'undefined') return;
  const element = (tag, text) => { const node = document.createElement(tag); if (text !== undefined) node.textContent = text; return node; };
  document.querySelectorAll('[data-sequence-sites]').forEach(root => {
    const records = JSON.parse(root.dataset.sequenceSites), target = root.querySelector('[data-sequence-target]'), panels = root.querySelector('[data-sequence-panels]');
    const allPanels = records.map((record,index) => {
      const option = element('option',`${record.target_id} · ${record.accession}`); option.value=String(index); target.append(option);
      const panel=element('div'); panel.hidden=index!==0;
      panel.append(element('p',`Accession ${record.accession} · isoform ${record.isoform || 'canonical'} · sequence source ${record.source_id} · ${record.length} residues`));
      const full=element('textarea'); full.readOnly=true; full.value=record.sequence; full.rows=4; full.setAttribute('aria-label','Exact canonical sequence'); panel.append(full);
      panel.append(element('p','Select text in the sequence to set an interval, or enter start and end positions.'));
      const start=element('input'), end=element('input'); start.type=end.type='number'; start.min=end.min='1'; start.max=end.max=String(record.length); start.value='1'; end.value=String(record.length);
      for(const [name,input] of [['Start',start],['End',end]]) {const label=element('label',name+' ');label.append(input);panel.append(label);}
      const annotation=element('ul'); record.extracellular.forEach(a=>annotation.append(element('li',`${a.start}–${a.end}: ${a.label} · source ${a.source_id}`))); panel.append(annotation);
      const fieldset=element('fieldset');fieldset.append(element('legend','Partners retained in the 3D scene and Codex request'));
      const boxes=record.partners.map(p=>{const label=element('label'),box=element('input');box.type='checkbox';box.value=p.partner_id;box.checked=true;label.append(box,document.createTextNode(`${p.label} · ${p.accession} · chain ${p.chain}`));fieldset.append(label);return box;});panel.append(fieldset);
      const status=element('p');status.setAttribute('role','status');panel.append(status);
      const view=element('button','Inspect verified residues in 3D');view.type='button';
      const download=element('button','Download exact FASTA');download.type='button';
      const copy=element('button','Copy Codex request');copy.type='button';
      const request=element('textarea');request.readOnly=true;request.rows=8;request.setAttribute('aria-label','Portable Codex request');
      const details=element('details');details.append(element('summary','Review the portable Codex request'),request);
      panel.append(view,download,copy,details);
      let current;
      function update() {
        try {
          current=selection(record,Number(start.value),Number(end.value),boxes.filter(b=>b.checked).map(b=>b.value));
          status.textContent=`${current.mapped} verified residues; ${current.context.unresolved_positions.length} unresolved positions in this interval. Author numbering and insertion codes are preserved.`;
          request.value=current.prompt;view.disabled=!current.mapped;download.disabled=copy.disabled=false;
          view.dataset.structurePreview=record.coordinates.path;view.dataset.structureFormat='pdb';view.dataset.structureScene=JSON.stringify(current.scene);view.dataset.structureTitle=`${record.accession} canonical ${start.value}–${end.value}`;view.dataset.structureId=record.target_id;view.dataset.structureEvidence='Verified explicit canonical-to-coordinate mapping';
        } catch(error) { current=null;status.textContent=error.message;view.disabled=download.disabled=copy.disabled=true;delete view.dataset.structurePreview;request.value=''; }
      }
      [start,end,...boxes].forEach(input=>input.addEventListener('change',update));
      full.addEventListener('select',()=>{if(full.selectionEnd>full.selectionStart){start.value=String(full.selectionStart+1);end.value=String(full.selectionEnd);update();}});
      download.addEventListener('click',()=>{if(!current)return;const url=URL.createObjectURL(new Blob([current.fasta],{type:'text/plain;charset=utf-8'}));const a=element('a');a.href=url;a.download=`${record.accession}-${start.value}-${end.value}.fasta`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
      copy.addEventListener('click',async()=>{if(!current)return;try{await navigator.clipboard.writeText(current.prompt);status.textContent='Codex request copied.';}catch(_){details.open=true;request.focus();request.select();status.textContent='Select and copy the request shown below.';}});
      update();panels.append(panel);return panel;
    });
    target.addEventListener('change',()=>allPanels.forEach((panel,index)=>{panel.hidden=String(index)!==target.value;}));
  });
})();
