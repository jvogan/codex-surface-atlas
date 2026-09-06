"""Synthetic author-numbered coordinates; no downloaded biological fixtures."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from surface_atlas.sequence_sites import SCHEMA_VERSION, render_sequence_sites, validate_sequence_sites


def fixture(root):
    lines = []
    for serial, (name, chain, number, insertion) in enumerate([('ALA','A',10,''),('CYS','A',10,'A'),('GLY','B',1,'')],1):
        lines.append(f'ATOM  {serial:5d}  CA  {name:3s} {chain}{number:4d}{insertion:1s}   {float(serial):8.3f}{0.:8.3f}{0.:8.3f}  1.00 20.00           C  ')
    data = ('\n'.join(lines)+'\nEND\n').encode()
    (root/'synthetic.pdb').write_bytes(data)
    sequence='ACD'
    return {'target_id':'synthetic-target','sequence_sites':{
        'schema_version':SCHEMA_VERSION,'accession':'SYNTHETIC-1','isoform':None,'source_id':'synthetic-sequence',
        'sequence':sequence,'length':3,'sequence_sha256':hashlib.sha256(sequence.encode()).hexdigest(),
        'coordinate_model':1,'numbering':'author',
        'coordinates':{'path':'synthetic.pdb','sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'format':'pdb'},
        'mappings':[{'canonical_position':1,'chain':'A','author_residue_number':10,'insertion_code':''},
                    {'canonical_position':2,'chain':'A','author_residue_number':10,'insertion_code':'A'}],
        'unresolved':[{'start':3,'end':3}],
        'extracellular':[{'start':1,'end':3,'label':'Synthetic annotation','source_id':'synthetic-topology'}],
        'partners':[{'partner_id':'synthetic-partner','accession':'SYNTHETIC-2','label':'Synthetic partner','chain':'B'}]}}


class SequenceSitesTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.target=fixture(self.root)
    def tearDown(self):
        self.tmp.cleanup()
    def test_valid_insertion_code_and_unresolved_gap(self):
        self.assertEqual(validate_sequence_sites(self.root,[self.target]),[])
        from jsonschema import Draft202012Validator
        schema=json.loads((Path(__file__).parents[1]/'schemas/v0.1/sequence-sites.schema.json').read_text())
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(self.target['sequence_sites'])
        body=render_sequence_sites([self.target],{'synthetic.pdb':'data/artifacts/synthetic.pdb'})
        self.assertIn('data-sequence-sites',body)
    def test_no_extension_remains_valid(self):
        self.assertEqual(validate_sequence_sites(self.root,[{'target_id':'legacy'}]),[])
    def test_rejects_ambiguous_or_incorrect_maps_and_metadata(self):
        mutations=[lambda r:r['mappings'][1].update(insertion_code=''),
                   lambda r:r['mappings'][1].update(canonical_position=1),
                   lambda r:r['mappings'][1].update(author_residue_number=99),
                   lambda r:r.update(unresolved=[]), lambda r:r['unresolved'][0].update(start=2),
                   lambda r:r.update(length=True),lambda r:r.update(sequence_sha256='0'*64),
                   lambda r:r.pop('isoform'),lambda r:r.update(accession=''),
                   lambda r:r['partners'][0].update(chain='A'),
                   lambda r:r['partners'].append(copy.deepcopy(r['partners'][0])),
                   lambda r:r['extracellular'][0].update(end=4),
                   lambda r:r['coordinates'].update(path='../synthetic.pdb'),
                   lambda r:r['coordinates'].update(sha256='0'*64)]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                target=copy.deepcopy(self.target);mutate(target['sequence_sites'])
                self.assertTrue(validate_sequence_sites(self.root,[target]))
    def test_duplicate_target_and_symlink_rejected(self):
        self.assertTrue(validate_sequence_sites(self.root,[self.target,self.target]))
        (self.root/'link.pdb').symlink_to(self.root/'synthetic.pdb')
        self.target['sequence_sites']['coordinates']['path']='link.pdb'
        self.assertTrue(validate_sequence_sites(self.root,[self.target]))
    def test_partner_chain_must_be_named_even_when_blank_chain_exists(self):
        for chain in (' ', '?', '_'):
            with self.subTest(chain=chain):
                target=fixture(self.root)
                path=self.root/'synthetic.pdb'
                data=path.read_bytes().replace(b'GLY B', ('GLY '+chain).encode())
                path.write_bytes(data)
                target['sequence_sites']['coordinates'].update(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
                target['sequence_sites']['partners'][0]['chain']=chain
                self.assertIn('partner chain/identity', ' '.join(validate_sequence_sites(self.root,[target])))
    def test_amino_acid_and_model_checks(self):
        for changed in [('CYS','GLY'),('END','MODEL        1\nENDMDL\nMODEL        2\nENDMDL')]:
            target=fixture(self.root);data=(self.root/'synthetic.pdb').read_bytes().replace(changed[0].encode(),changed[1].encode())
            (self.root/'synthetic.pdb').write_bytes(data)
            target['sequence_sites']['coordinates'].update(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
            self.assertTrue(validate_sequence_sites(self.root,[target]))
    def test_nonfinite_or_unparseable_coordinates_rejected_with_valid_file_hash(self):
        for column in (30, 38, 46):
            for coordinate in ('nan', 'inf', '-inf', 'garbage', ''):
                with self.subTest(column=column, coordinate=coordinate):
                    target=fixture(self.root)
                    lines=(self.root/'synthetic.pdb').read_text().splitlines()
                    lines[0]=lines[0][:column]+coordinate.rjust(8)+lines[0][column+8:]
                    data=('\n'.join(lines)+'\n').encode()
                    (self.root/'synthetic.pdb').write_bytes(data)
                    target['sequence_sites']['coordinates'].update(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
                    self.assertIn('finite', ' '.join(validate_sequence_sites(self.root,[target])))
    @unittest.skipUnless(shutil.which('node'), 'Node is needed for browser logic checks')
    def test_browser_selection_fasta_handoff_and_partner_identity(self):
        script=Path(__file__).parents[1]/'src/surface_atlas/assets/report/sequence-sites.js'
        record={**self.target['sequence_sites'],'target_id':self.target['target_id']}
        code="""const assert=require('node:assert/strict'); const {selection}=require(process.argv[1]);const r=JSON.parse(process.argv[2]);
        const s=selection(r,2,3,['synthetic-partner']);assert.equal(s.mapped,1);assert.equal(s.context.sequence,'CD');assert.deepEqual(s.context.unresolved_positions,[3]);assert.equal(s.scene.layers[0].verified_residues[0].insertion_code,'A');assert.equal(s.context.partners[0].accession,'SYNTHETIC-2');assert.match(s.fasta,/\\nCD\\n$/);assert.ok(s.prompt.includes(r.sequence_sha256));assert.ok(s.prompt.includes(r.coordinates.sha256));assert.equal(selection(r,1,1,[]).context.partners.length,0);assert.equal(s.context.partners.length,1);assert.throws(()=>selection(r,0,2,[]));assert.equal(selection(r,3,3,[]).mapped,0);
        const hash=value=>require('node:crypto').createHash('sha256').update(value,'ascii').digest('hex');
        assert.equal(hash(s.context.canonical_sequence),s.context.canonical_sequence_sha256);assert.notEqual(hash(s.context.sequence),s.context.canonical_sequence_sha256);assert.equal(s.context.canonical_sequence.slice(s.context.canonical_range.start-1,s.context.canonical_range.end),s.context.sequence);assert.match(s.context.sequence_scope,/selected canonical interval/);"""
        subprocess.run(['node','-e',code,str(script),json.dumps(record)],check=True,capture_output=True,text=True)

    @unittest.skipUnless(shutil.which('node'), 'Node is needed for browser logic checks')
    def test_browser_selects_exact_insertion_code_and_rechecks_identity(self):
        script=(Path(__file__).parents[1]/'src/surface_atlas/assets/report/structure-preview.js').read_text(encoding='utf-8')
        start=script.index('      let selected = model.selectedAtoms(layer.selection);')
        end=script.index('      const selection = layer.verified_residues',start)
        helper='function select(model, layer) {\n'+script[start:end]+'\nreturn selected;\n}'
        probe=helper+"""
const assert=require('node:assert/strict');
const atoms=[{chain:'A',resi:10,icode:'',resn:'ALA',index:0},{chain:'A',resi:10,icode:'A',resn:'CYS',index:1},{chain:'B',resi:10,icode:'A',resn:'CYS',index:2}].map(a=>({...a,x:0,y:1,z:2}));
const model={selectedAtoms:q=>atoms.filter(a=>(q.chain===undefined||a.chain===q.chain)&&(q.resi===undefined||a.resi===q.resi))};
const residue={chain:'A',author_residue_number:10,insertion_code:'A',amino_acid:'C'};
assert.deepEqual(select(model,{selection:{},verified_residues:[residue]}).map(a=>a.index),[1]);
assert.throws(()=>select(model,{selection:{},verified_residues:[{...residue,amino_acid:'A'}]}));
assert.throws(()=>select(model,{selection:{},verified_residues:[{...residue,insertion_code:'B'}]}));
assert.throws(()=>select(model,{selection:{},verified_residues:[residue,residue]}));
for(const value of [NaN,Infinity,undefined,'1']) { atoms[1].x=value;assert.throws(()=>select(model,{selection:{},verified_residues:[residue]})); }
"""
        subprocess.run(['node','-e',probe],check=True,capture_output=True,text=True)


if __name__=='__main__':
    unittest.main()
