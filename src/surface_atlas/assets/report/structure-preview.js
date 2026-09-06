/* One molecular scene per page. Coordinates and 3Dmol load only after a click. */
(() => {
  'use strict';
  const scriptURL = document.currentScript && document.currentScript.src;
  if (!scriptURL) return;
  const reportRoot = new URL('../', scriptURL);
  const libraryURL = new URL('vendor/3Dmol-2.5.5.min.js', scriptURL);
  const MAX_BYTES = 8 * 1024 * 1024;
  const MAX_ATOMS = 60000;
  const formats = { pdb: 'pdb', cif: 'cif', mmcif: 'cif', sdf: 'sdf' };
  let dialog, stage, status, heading, metadata, download, viewer, opener;
  let libraryPromise, controller, requestID = 0, ready = false;
  let sceneLayers = [], homeSelection = {};
  let residueLabel = null;
  let handoffDialog, handoffText, handoffStatus, handoffCopy, handoffOpener, handoffRequest = 0;

  function portableText(value) {
    if (typeof value !== 'string' || value.startsWith('/') || /^[A-Za-z]:[\\/]/.test(value) || value.includes('\\')) return '';
    return value.replace(/[\u0000-\u001f\u007f]/g, ' ').trim();
  }

  function artifactPath(value) {
    if (typeof value !== 'string' || !value.startsWith('data/artifacts/') ||
        /[\u0000-\u001f\u007f\\?#]/.test(value) ||
        value.split('/').some(part => !part || part === '..' || part === '.') ||
        !/\.(?:pdb|cif|mmcif|sdf|fasta|fa|faa)$/i.test(value)) throw new Error('Missing packaged file');
    return value;
  }

  function handoffMetadata(button) {
    const figure = {
      id: portableText(button.dataset.structureId),
      title: portableText(button.dataset.structureTitle),
      evidence: portableText(button.dataset.structureEvidence),
    };
    const scene = button.dataset.structureScene ? JSON.parse(button.dataset.structureScene) : null;
    const sources = scene ? scene.sources : [{href: button.dataset.structurePreview, format: button.dataset.structureFormat}];
    if (!Array.isArray(sources) || !sources.length || sources.length > 4) throw new Error('Missing coordinate sources');
    const coordinates = sources.map(source => {
      const item = {path: artifactPath(source.href), format: portableText(source.format)};
      if (/^[a-f0-9]{64}$/.test(source.sha256)) item.sha256 = source.sha256;
      if (source.object_name) item.object_name = portableText(source.object_name);
      if (Number.isInteger(source.state) && source.state > 0) item.state = source.state;
      return item;
    });
    const metadata = {figure, coordinates};
    if (scene) {
      metadata.selection_format = '3Dmol SelectionSpec; author chain and residue numbering';
      if (!Array.isArray(scene.layers) || scene.layers.length > 20) throw new Error('Missing molecular parts');
      metadata.layers = scene.layers.map(layer => {
        const selection = layer.selection;
        if (!selection || Object.keys(selection).some(key => !['chain','resi','resn','hetflag','elem','invert'].includes(key))) {
          throw new Error('Unsupported selection');
        }
        for (const value of Object.values(selection)) {
          const values = Array.isArray(value) ? value : [value];
          if (values.some(item => !['string','number','boolean'].includes(typeof item) ||
              (typeof item === 'string' && portableText(item) !== item))) throw new Error('Unsupported selection value');
        }
        return {
          label: portableText(layer.label), object_name: portableText(layer.object_name),
          color: portableText(layer.color), representation: portableText(layer.representation),
          opacity: layer.opacity, elements: layer.elements, selection,
        };
      });
    } else if (button.dataset.structureChains) {
      const labels = JSON.parse(button.dataset.structureChains);
      metadata.chain_labels = Object.fromEntries(Object.entries(labels).map(([chain, label]) => [portableText(chain), portableText(label)]));
    }
    if (button.dataset.structureSequence) {
      const sequence = JSON.parse(button.dataset.structureSequence);
      const path = artifactPath(sequence.path);
      if (!path.endsWith('.fasta') && !path.endsWith('.fa') && !path.endsWith('.faa')) throw new Error('Unsupported sequence file');
      if (!/^[a-f0-9]{64}$/.test(sequence.sha256)) throw new Error('Unsupported sequence hash');
      metadata.sequence = {
        path,
        sha256: sequence.sha256,
        bytes: Number.isInteger(sequence.bytes) ? sequence.bytes : undefined,
        sequence_id: portableText(sequence.sequence_id),
        chain: portableText(sequence.chain),
      };
    }
    return metadata;
  }

  function requestText(metadata) {
    const lines = [
      'Open “' + (metadata.figure.title || metadata.figure.id || 'this report figure') + '” in Codex’s Molecular Structure Viewer and explain the molecular parts.',
      'Use the exact report files below. Verify their supplied hashes and reproduce the recorded chain labels, colors, and selections in one viewer. Preserve the evidence label and author residue numbering.',
    ];
    if (metadata.layers) lines.push('Translate the recorded 3Dmol selectors into native viewer selections.');
    if (metadata.sequence) lines.push('Then open the matching FASTA in Biological Sequence Viewer. Verify its recorded identity and map sequence positions to the structure’s author residues before transferring a selection.');
    lines.push('Use the installed viewer tools in this conversation and confirm loading.',
      'Figure and source files:', JSON.stringify(metadata, null, 2));
    return lines.join('\n\n');
  }

  function createHandoffDialog() {
    if (handoffDialog) return;
    handoffDialog = document.createElement('dialog');
    handoffDialog.className = 'structure-handoff-dialog';
    handoffDialog.setAttribute('aria-labelledby', 'structure-handoff-title');
    handoffDialog.setAttribute('aria-describedby', 'structure-handoff-help');
    handoffDialog.innerHTML = `<header><h2 id="structure-handoff-title">Copy Codex request</h2><button type="button" data-handoff-close aria-label="Close Codex request">Close</button></header>
      <div class="structure-handoff-body"><p id="structure-handoff-help">Copy this request into your Codex conversation with the report files available. Codex uses the figure’s recorded files to open the native viewers.</p>
      <label for="structure-handoff-text">Request for this figure</label><textarea id="structure-handoff-text" readonly spellcheck="false" rows="14"></textarea>
      <div class="structure-handoff-actions"><button type="button" data-handoff-copy>Copy request</button><button type="button" data-handoff-select>Select request</button></div>
      <p class="structure-handoff-status" role="status" aria-live="polite"></p></div>`;
    document.body.append(handoffDialog);
    handoffText = handoffDialog.querySelector('textarea');
    handoffStatus = handoffDialog.querySelector('[role="status"]');
    handoffCopy = handoffDialog.querySelector('[data-handoff-copy]');
    handoffDialog.querySelector('[data-handoff-close]').addEventListener('click', () => handoffDialog.close());
    handoffDialog.addEventListener('close', () => {
      handoffRequest += 1;
      if (handoffOpener?.isConnected) handoffOpener.focus();
    });
    handoffDialog.querySelector('[data-handoff-select]').addEventListener('click', () => {
      handoffText.focus(); handoffText.select();
      handoffStatus.textContent = 'Request selected. Press Command+C or Ctrl+C to copy.';
    });
    handoffCopy.addEventListener('click', async () => {
      const request = handoffRequest;
      try {
        if (!navigator.clipboard?.writeText) throw new Error('Clipboard unavailable');
        await navigator.clipboard.writeText(handoffText.value);
        if (request === handoffRequest) handoffStatus.textContent = 'Request copied. Paste it into your Codex conversation.';
      } catch (_) {
        if (request !== handoffRequest) return;
        handoffText.focus(); handoffText.select();
        handoffStatus.textContent = 'Clipboard access is unavailable. The request is selected; press Command+C or Ctrl+C to copy.';
      }
    });
  }

  async function openHandoff(button, trigger) {
    createHandoffDialog();
    const request = ++handoffRequest;
    handoffOpener = trigger;
    handoffCopy.disabled = true;
    handoffDialog.querySelector('[data-handoff-select]').disabled = true;
    handoffText.value = '';
    handoffStatus.textContent = 'Preparing the figure’s request…';
    if (!handoffDialog.open) handoffDialog.showModal();
    handoffDialog.querySelector('[data-handoff-close]').focus();
    try {
      const metadata = handoffMetadata(button);
      if (request !== handoffRequest || !handoffDialog.open) return;
      handoffText.value = requestText(metadata);
      handoffCopy.disabled = false;
      handoffDialog.querySelector('[data-handoff-select]').disabled = false;
      handoffStatus.textContent = 'Review the request, then copy it into Codex.';
    } catch (_) {
      if (request === handoffRequest) handoffStatus.textContent = 'The figure metadata could not form a request. Use the figure’s coordinate download and ask Codex to open that file.';
    }
  }

  function addHandoffButtons() {
    document.querySelectorAll('[data-structure-preview]').forEach(button => {
      if (button.nextElementSibling?.classList.contains('structure-handoff-trigger')) return;
      const trigger = document.createElement('button');
      trigger.type = 'button'; trigger.className = 'structure-handoff-trigger';
      trigger.textContent = 'Copy Codex request';
      trigger.setAttribute('aria-haspopup', 'dialog');
      trigger.setAttribute('aria-label', 'Copy Codex request for ' + (portableText(button.dataset.structureTitle) || 'this structure'));
      trigger.addEventListener('click', () => openHandoff(button, trigger));
      button.after(trigger);
    });
  }

  function coordinates(href, format) {
    const url = new URL(href, document.baseURI);
    const prefix = new URL('data/artifacts/', reportRoot).pathname;
    const path = decodeURIComponent(url.pathname);
    if (!['http:', 'https:'].includes(url.protocol) || url.origin !== reportRoot.origin ||
        !path.startsWith(prefix) || path.includes('\\') || url.search || url.hash ||
        url.username || url.password || path.split('/').includes('..')) {
      throw new Error('Open the report through its local server to preview packaged coordinates.');
    }
    const suffix = path.split('.').pop().toLowerCase();
    if (!formats[suffix] || formats[suffix] !== format) {
      throw new Error('Preview supports PDB, mmCIF, and SDF files. Download this file to open it in a molecular viewer.');
    }
    return url;
  }

  function loadLibrary() {
    if (!libraryPromise) {
      libraryPromise = new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = libraryURL.href;
        script.async = true;
        script.onload = () => window.$3Dmol ? resolve(window.$3Dmol) : reject(new Error('The 3D library did not load. Download the coordinates to open them in a molecular viewer.'));
        script.onerror = () => {
          script.remove();
          libraryPromise = null;
          reject(new Error('The 3D library could not load. Download the coordinates to open them in a molecular viewer.'));
        };
        document.head.append(script);
      });
    }
    return libraryPromise;
  }

  async function readCoordinates(url, signal) {
    const response = await fetch(url.href, { signal, credentials: 'same-origin', redirect: 'error' });
    if (!response.ok) throw new Error('The coordinate file could not load. Try the download link.');
    if (Number(response.headers.get('content-length')) > MAX_BYTES) {
      await response.body?.cancel();
      throw new Error('This file exceeds the 8 MB preview limit. Download it to open in a molecular viewer.');
    }
    if (!response.body) throw new Error('The browser could not read this file. Try the download link.');
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    const chunks = [];
    let size = 0;
    try {
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        size += value.byteLength;
        if (size > MAX_BYTES) {
          await reader.cancel();
          throw new Error('This file exceeds the 8 MB preview limit. Download it to open in a molecular viewer.');
        }
        chunks.push(decoder.decode(value, { stream: true }));
      }
    } finally { reader.releaseLock(); }
    chunks.push(decoder.decode());
    return chunks.join('');
  }

  function setReady(value) {
    ready = value;
    dialog.querySelectorAll('[data-viewer-action]').forEach(button => { button.disabled = !value; });
    if (value) stage.setAttribute('aria-busy', 'false');
  }

  function clearScene() {
    clearResidueLabel();
    if (stage) stage.querySelector('.structure-preview-focus-name').hidden = true;
    if (viewer) { viewer.clear(); viewer.render(); }
    sceneLayers = [];
    homeSelection = {};
    if (dialog) {
      setReady(false);
      dialog.querySelector('.structure-preview-chain-key').textContent = '';
      dialog.querySelector('.structure-preview-parts').replaceChildren();
    }
  }

  function clearResidueLabel() {
    if (viewer && residueLabel) viewer.removeLabel(residueLabel);
    residueLabel = null;
    const hover = stage?.querySelector('.structure-preview-hover');
    if (hover) hover.hidden = true;
  }

  function residueText(atom) {
    return `${atom.resn || 'Residue'} ${atom.resi ?? ''}${atom.icode || ''} · chain ${atom.chain || '(unnamed)'}`;
  }

  function configurePicking(selection) {
    viewer.setClickable({}, false);
    viewer.setHoverable({}, false);
    viewer.setHoverDuration(150);
    viewer.setHoverable(selection, true, atom => {
      const hint = stage.querySelector('.structure-preview-hover');
      hint.textContent = residueText(atom) + ' — click to pin label'; hint.hidden = false;
    }, () => { stage.querySelector('.structure-preview-hover').hidden = true; });
    viewer.setClickable(selection, true, atom => {
      clearResidueLabel();
      residueLabel = viewer.addLabel(residueText(atom), {
        position: atom, font: 'sans-serif', fontSize: 18, fontColor: '#183e30',
        backgroundColor: '#FFFFFF', backgroundOpacity: .95, borderColor: '#829b90',
        borderThickness: 1, padding: 6, inFront: true,
      });
      const part = sceneLayers.find(layer => layer.visible && layer.atomSet.has(atom));
      status.textContent = `${part ? part.label + ' · ' : ''}${residueText(atom)} · atom ${atom.atom || atom.elem}. Author residue numbering.`;
      viewer.render();
    });
  }

  function zoomToPart(layer) {
    viewer.zoomTo(layer.selection); viewer.render();
    const points = viewer.modelToScreen([...layer.atomSet]);
    const xs = points.map(point => point.x), ys = points.map(point => point.y);
    const left = Math.min(...xs), right = Math.max(...xs), top = Math.min(...ys), bottom = Math.max(...ys);
    const rect = stage.getBoundingClientRect();
    const scale = Math.min(rect.width * .74 / Math.max(1, right-left), rect.height * .74 / Math.max(1, bottom-top));
    viewer.translateScene(rect.left + window.scrollX + rect.width/2 - (left+right)/2,
      rect.top + window.scrollY + rect.height/2 - (top+bottom)/2);
    viewer.zoom(Math.max(.25, Math.min(8, scale))); viewer.render();
    const name = stage.querySelector('.structure-preview-focus-name');
    name.textContent = layer.label; name.hidden = false;
    status.textContent = `Zoomed to ${layer.label.replace(/[.\s]+$/, '')}.`;
    stage.scrollIntoView({block:'nearest', behavior:'instant'});
  }

  function closePreview() {
    requestID += 1;
    controller?.abort();
    controller = null;
    clearScene();
    stage.setAttribute('aria-busy', 'false');
    if (opener?.isConnected) opener.focus();
  }

  function createDialog() {
    if (dialog) return;
    dialog = document.createElement('dialog');
    dialog.className = 'structure-preview-dialog';
    dialog.setAttribute('aria-labelledby', 'structure-preview-title');
    dialog.setAttribute('aria-describedby', 'structure-preview-meta structure-preview-help');
    dialog.innerHTML = `<header><div><h2 id="structure-preview-title"></h2><p id="structure-preview-meta" class="structure-preview-meta"></p></div><button type="button" data-viewer-close aria-label="Close structure preview">Close</button></header>
      <div class="structure-preview-stage" role="img" aria-label="Interactive molecular structure"><div class="structure-preview-focus-name" hidden></div><div class="structure-preview-hover" hidden></div></div>
      <p class="structure-preview-status" role="status" aria-live="polite"></p>
      <div class="structure-preview-footer"><div class="structure-preview-toolbar">
        <button type="button" data-viewer-action="reset">Reset view</button>
        <button type="button" data-viewer-action="left" aria-label="Rotate structure left">Rotate left</button>
        <button type="button" data-viewer-action="right" aria-label="Rotate structure right">Rotate right</button>
        <button type="button" data-viewer-action="up" aria-label="Rotate structure up">Rotate up</button>
        <button type="button" data-viewer-action="down" aria-label="Rotate structure down">Rotate down</button>
        <button type="button" data-viewer-action="in">Zoom in</button>
        <button type="button" data-viewer-action="out">Zoom out</button>
        <button type="button" data-viewer-action="all">Show all parts</button>
        <button type="button" data-viewer-action="clear">Clear residue label</button>
        <a data-viewer-download download>Download coordinates</a></div>
        <div class="structure-preview-parts" aria-label="Molecular parts"></div>
        <p class="structure-preview-chain-key"></p>
        <p class="structure-preview-help" id="structure-preview-help">Drag to rotate; scroll or pinch to zoom. Hover over a residue to identify it; click to pin its label. Zoom to a part for a closer view, or show it on its own. Interactive rendering uses 3Dmol.js.</p>
        <details class="structure-preview-workbench"><summary>Continue in the Rosalind workbench</summary><p>Open the coordinate file in Codex’s Molecular Structure Viewer for residue measurements, contacts, and saved scenes. Open a report FASTA file in Biological Sequence Viewer to search or compare sequences. The figure’s render settings record its chain labels and colors.</p></details></div>`;
    document.body.append(dialog);
    stage = dialog.querySelector('.structure-preview-stage');
    status = dialog.querySelector('.structure-preview-status');
    heading = dialog.querySelector('h2');
    metadata = dialog.querySelector('.structure-preview-meta');
    download = dialog.querySelector('[data-viewer-download]');
    dialog.querySelector('[data-viewer-close]').addEventListener('click', () => dialog.close());
    dialog.addEventListener('close', closePreview);
    dialog.addEventListener('click', event => {
      const action = event.target.closest('[data-viewer-action]')?.dataset.viewerAction;
      if (!ready || !action) return;
      if (action === 'reset') { viewer.setView(viewer.homeView); stage.querySelector('.structure-preview-focus-name').hidden = true; }
      if (action === 'clear') { clearResidueLabel(); status.textContent = 'Residue label cleared. Hover or click another residue.'; }
      if (action === 'all') {
        clearResidueLabel(); stage.querySelector('.structure-preview-focus-name').hidden = true;
        sceneLayers.forEach(layer => { layer.visible = true; });
        dialog.querySelectorAll('.structure-preview-parts input').forEach(input => { input.checked = true; });
        if (sceneLayers.length) applyLayers();
        viewer.setView(viewer.homeView);
        status.textContent = 'All molecular parts shown. Drag to rotate; scroll to zoom.';
      }
      if (action === 'left') viewer.rotate(-20, 'y');
      if (action === 'right') viewer.rotate(20, 'y');
      if (action === 'up') viewer.rotate(-20, 'x');
      if (action === 'down') viewer.rotate(20, 'x');
      if (action === 'in') viewer.zoom(1.2);
      if (action === 'out') viewer.zoom(0.8);
      viewer.render();
    });
    new ResizeObserver(() => { if (viewer && dialog.open) { viewer.resize(); viewer.render(); } }).observe(stage);
  }

  function applyLayers() {
    viewer.setStyle({}, {});
    for (const layer of sceneLayers) {
      if (!layer.visible) continue;
      const style = { color: layer.color, opacity: layer.opacity };
      if (layer.representation === 'stick') {
        style.radius = .18;
        if (layer.elements) style.colorfunc = atom => atom.elem === 'C' ? layer.color :
          ({O:'#D44848',N:'#4169C1',S:'#C7A327',P:'#C07832',F:'#64A553',Cl:'#64A553',Br:'#A65340'}[atom.elem] || '#879298');
      }
      viewer.addStyle(layer.selection, { [layer.representation]: style });
    }
    const visible = sceneLayers.filter(layer => layer.visible);
    configurePicking(visible.length ? {or:visible.map(layer=>layer.selection)} : {index:-1});
    viewer.render();
  }

  function partsControls() {
    const parts = dialog.querySelector('.structure-preview-parts');
    for (const layer of sceneLayers) {
      const row = document.createElement('div');
      row.className = 'structure-preview-part';
      const label = document.createElement('label');
      const input = document.createElement('input');
      input.type = 'checkbox'; input.checked = true;
      input.addEventListener('change', () => { clearResidueLabel(); layer.visible = input.checked; stage.querySelector('.structure-preview-focus-name').hidden = true; applyLayers(); });
      const dot = document.createElement('span');
      dot.className = 'structure-preview-dot'; dot.style.backgroundColor = layer.color;
      dot.setAttribute('aria-hidden', 'true');
      const text = document.createElement('span'); text.textContent = layer.label;
      label.append(input, dot, text);
      const focus = document.createElement('button');
      focus.type = 'button'; focus.textContent = 'Zoom to part';
      focus.setAttribute('aria-label', 'Zoom to ' + layer.label);
      focus.addEventListener('click', () => {
        clearResidueLabel(); layer.visible = true; input.checked = true; applyLayers(); zoomToPart(layer);
      });
      const only = document.createElement('button');
      only.type = 'button'; only.textContent = 'Show only'; only.setAttribute('aria-label', 'Show only ' + layer.label);
      only.addEventListener('click', () => {
        clearResidueLabel(); sceneLayers.forEach(part=>{part.visible = part === layer;});
        parts.querySelectorAll('input').forEach((checkbox,index)=>{checkbox.checked=sceneLayers[index].visible;});
        applyLayers(); zoomToPart(layer); status.textContent = `Showing only ${layer.label.replace(/[.\s]+$/, '')}. Use Show all parts to restore the complex.`;
      });
      row.append(label, focus, only); parts.append(row);
    }
  }

  async function loadRecordedScene(scene, library, currentID) {
    if (!Array.isArray(scene.sources) || !scene.sources.length || scene.sources.length > 4 ||
        !Array.isArray(scene.layers) || !scene.layers.length || scene.layers.length > 20) {
      throw new Error('The figure has no supported interactive scene. Use its coordinate download.');
    }
    if (!viewer) viewer = library.createViewer(stage, { backgroundColor: 'white', antialias: true });
    viewer.setProjection('orthographic');
    const models = new Map(); let count = 0, bytes = 0;
    for (const source of scene.sources) {
      if (source.state !== 1 || !/^[a-f0-9]{64}$/.test(source.sha256)) throw new Error('The coordinate model or hash is unsupported.');
      const url = coordinates(source.href, source.format);
      const data = await readCoordinates(url, controller.signal);
      if (currentID !== requestID || !dialog.open) return;
      const encoded = new TextEncoder().encode(data); bytes += encoded.byteLength;
      if (bytes > MAX_BYTES) throw new Error('This scene exceeds the 8 MB preview limit.');
      const digest = [...new Uint8Array(await crypto.subtle.digest('SHA-256', encoded))].map(x => x.toString(16).padStart(2,'0')).join('');
      if (digest !== source.sha256) throw new Error('The coordinates do not match the figure’s recorded file hash.');
      if (currentID !== requestID || !dialog.open) return;
      const model = viewer.addModel(data, source.format, {keepH:false, doAssembly:false});
      const atoms = model.selectedAtoms({}); count += atoms.length;
      if (!atoms.length || count > MAX_ATOMS) throw new Error('This scene is empty or exceeds the 60,000-atom preview limit.');
      if (atoms.some(atom=>![atom.x,atom.y,atom.z].every(Number.isFinite))) throw new Error('The coordinates contain invalid or nonfinite atom positions.');
      models.set(source.object_name, model);
    }
    sceneLayers = scene.layers.map(layer => {
      const model = models.get(layer.object_name);
      if (!model || !/^#[a-f0-9]{6}$/i.test(layer.color) || !['cartoon','stick'].includes(layer.representation) ||
          !Number.isFinite(layer.opacity) || layer.opacity < 0 || layer.opacity > 1) throw new Error('The figure’s molecular styling is unsupported.');
      const allowed = ['chain','resi','resn','hetflag','elem','invert'];
      if (!layer.selection || Object.keys(layer.selection).some(k => !allowed.includes(k))) throw new Error('The figure’s atom selection is unsupported.');
      let selected = model.selectedAtoms(layer.selection);
      if (layer.verified_residues !== undefined) {
        const names = {ALA:'A',ARG:'R',ASN:'N',ASP:'D',CYS:'C',GLN:'Q',GLU:'E',GLY:'G',HIS:'H',ILE:'I',LEU:'L',LYS:'K',MET:'M',PHE:'F',PRO:'P',SER:'S',THR:'T',TRP:'W',TYR:'Y',VAL:'V',SEC:'U',PYL:'O'};
        if (!Array.isArray(layer.verified_residues) || !layer.verified_residues.length || layer.verified_residues.length > 10000) throw new Error('The explicit residue map is unsupported.');
        selected = [];
        const seen = new Set();
        for (const residue of layer.verified_residues) {
          const key = JSON.stringify([residue.chain,residue.author_residue_number,residue.insertion_code]);
          if (seen.has(key) || !Number.isInteger(residue.author_residue_number) || typeof residue.insertion_code !== 'string') throw new Error('The explicit residue map is ambiguous.');
          seen.add(key);
          const atoms = model.selectedAtoms({chain:residue.chain,resi:residue.author_residue_number}).filter(atom=>!atom.hetflag && (atom.icode || '') === residue.insertion_code);
          if (!atoms.length || atoms.some(atom=>names[atom.resn] !== residue.amino_acid || ![atom.x,atom.y,atom.z].every(Number.isFinite))) throw new Error('The selected residue does not match its verified amino acid, finite coordinates and author numbering.');
          selected.push(...atoms);
        }
      }
      const selection = layer.verified_residues ? {index:selected.map(atom=>atom.index),model:model.getID()} : {...layer.selection, model:model.getID()};
      if (!selected.length) throw new Error('The named chain or residue is missing from these coordinates.');
      return {...layer, selection, atomSet:new Set(selected), visible:true};
    });
    homeSelection = {or:sceneLayers.map(layer => layer.selection)};
    applyLayers(); partsControls();
    dialog.querySelector('.structure-preview-chain-key').textContent = 'Colors and molecular parts follow the recorded preview selections. Residue labels use author chain IDs and numbering.';
    viewer.resize(); viewer.zoomTo(homeSelection);
    if (stage.clientWidth < 600) viewer.zoom(1.4);
    viewer.render(); viewer.homeView = viewer.getView();
    setReady(true);
    status.textContent = `${count.toLocaleString()} atoms loaded. Choose a part below or drag to rotate.`;
  }

  async function openPreview(button) {
    createDialog();
    controller?.abort();
    const currentID = ++requestID;
    controller = new AbortController();
    opener = button;
    clearScene();
    heading.textContent = button.dataset.structureTitle || 'Structure preview';
    metadata.textContent = [button.dataset.structureId, button.dataset.structureEvidence].filter(Boolean).join(' · ');
    stage.setAttribute('aria-label', `Molecular structure: ${heading.textContent}`);
    status.textContent = 'Loading structure…';
    stage.setAttribute('aria-busy', 'true');
    download.removeAttribute('href');
    if (!dialog.open) dialog.showModal();
    dialog.querySelector('[data-viewer-close]').focus();
    try {
      if (button.dataset.structureScene) {
        const scene = JSON.parse(button.dataset.structureScene);
        download.href = coordinates(scene.sources[0].href, scene.sources[0].format).href;
        const library = await loadLibrary();
        if (currentID !== requestID || !dialog.open) return;
        await loadRecordedScene(scene, library, currentID);
        return;
      }
      const format = button.dataset.structureFormat;
      const url = coordinates(button.dataset.structurePreview, format);
      download.href = url.href;
      const [library, data] = await Promise.all([loadLibrary(), readCoordinates(url, controller.signal)]);
      if (currentID !== requestID || !dialog.open) return;
      if (!viewer) viewer = library.createViewer(stage, { backgroundColor: 'white', antialias: true });
      const model = viewer.addModel(data, format, { keepH: false, doAssembly: false });
      const atoms = model.selectedAtoms({});
      if (!atoms.length) throw new Error('This file contains no readable atoms. Download it to inspect the coordinates.');
      if (atoms.length > MAX_ATOMS) throw new Error('This structure exceeds the 60,000-atom preview limit. Download it to open in a molecular viewer.');
      const chains = [...new Set(atoms.filter(atom => !atom.hetflag && atom.chain !== undefined).map(atom => atom.chain))].sort();
      const palette = [{hex:'#247562',name:'green'},{hex:'#386ba8',name:'blue'},{hex:'#aa702c',name:'gold'},{hex:'#ac5672',name:'rose'},{hex:'#7960a5',name:'violet'},{hex:'#62777e',name:'gray'}];
      viewer.setStyle({}, format === 'sdf' ? { stick: { radius: .18 } } : { cartoon: { colorfunc: atom => palette[Math.max(0, chains.indexOf(atom.chain)) % palette.length].hex } });
      let chainLabels = {};
      try { chainLabels = JSON.parse(button.dataset.structureChains || '{}'); } catch (_) { /* Chain IDs remain available. */ }
      dialog.querySelector('.structure-preview-chain-key').textContent = chains.map((chain, index) => `${palette[index % palette.length].name}: ${chainLabels[chain] || 'chain ' + (chain || '(unnamed)')}${chainLabels[chain] ? ' (chain ' + chain + ')' : ''}`).join(' · ');
      if (format !== 'sdf') viewer.setStyle({ hetflag: true }, { stick: { radius: .15 } });
      viewer.setStyle({ resn: ['HOH', 'WAT', 'DOD'] }, {});
      configurePicking({not:{resn:['HOH','WAT','DOD']}});
      viewer.resize();
      viewer.zoomTo();
      viewer.render();
      viewer.homeView = viewer.getView();
      setReady(true);
      status.textContent = `${atoms.length.toLocaleString()} atoms loaded. Use the controls or drag the structure.`;
    } catch (error) {
      if (currentID !== requestID || error.name === 'AbortError') return;
      controller?.abort();
      clearScene();
      stage.setAttribute('aria-busy', 'false');
      status.textContent = /^(This |The |Open |Preview )/.test(error.message || '')
        ? error.message : 'The 3D preview could not open. Download the coordinates to open them in a molecular viewer.';
    }
  }

  document.addEventListener('click', event => {
    const button = event.target.closest('[data-structure-preview]');
    if (button) openPreview(button);
  });
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', addHandoffButtons, {once: true});
  else addHandoffButtons();
})();
