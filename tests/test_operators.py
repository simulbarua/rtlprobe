"""In-memory syntax/mutation fixtures; temporary evidence roots; no simulations."""
import copy
import difflib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from rtlprobe.candidates import extract_candidates, mapping_coverage
from rtlprobe.mutation import (NEW_OPERATORS, apply, locate, locate_constant, locate_operator,
                               reachable_sites, revert, sha)
from rtlprobe.sv_frontend import Source

ROOT = Path(__file__).resolve().parents[1]
REL = 'relational_operator_replace'
COND = 'condition_invert'
LOGIC = 'logic_operator_swap'


def fixture(statement, declarations='logic [31:0] a, b, y;'):
    return ('module m;\n' + declarations + '\nalways_comb begin\n' + statement + '\nend\nendmodule\n').encode()


def locate_new(data, op, line=4, path='design.sv', resets=()):
    return locate_operator(data, line, op, data.decode().splitlines()[line - 1].strip(),
                           path=path, reset_identifiers=resets)


def approved(op):
    return {'id': op, 'version': '1.0', 'status': 'approved'}


class OperatorTests(unittest.TestCase):
    def test_relational_pairs_exact_roundtrip(self):
        for before, after in [('>=','>'),('>','>='),('<=','<'),('<','<='),('==','!='),('!=','==')]:
            with self.subTest(before=before):
                data = fixture(f'y = a {before} b;')
                target = locate_new(data, REL)
                self.assertEqual(target['before'], before)
                self.assertEqual(target['after'], after)
                changed = apply(data, target, approved(REL))
                self.assertEqual(changed, fixture(f'y = a {after} b;'))
                self.assertEqual(revert(changed, target), data)
                with self.assertRaises(ValueError): apply(changed, target, approved(REL))
                with self.assertRaises(ValueError): revert(changed+b' ', target)

    def test_known_width_selects_literals_and_signed(self):
        for expr in ["a[7:0] >= 8'h12", 'a[0] == b[0]', 'a >= b']:
            data = fixture('y = '+expr+';', 'logic signed [31:0] a,b,y;')
            locate_new(data, REL)

    def test_relational_exclusions(self):
        for statement in ['y = a === b;', 'y = a !== b;', 'y = missing >= b;',
                          'y = (a+1) >= b;', 'y = (a>b) || (a<b);', 'y = (a>b) || (a===b);', '// y = a >= b;',
                          '$display("a >= b");', 'y = a >=\n b;']:
            with self.subTest(statement=statement), self.assertRaises(ValueError):
                locate_new(fixture(statement), REL)
        data = b'module m;\nparameter N=1;\ngenerate\nif(N>=1) begin : g\nwire a;\nend\nendgenerate\nendmodule\n'
        with self.assertRaises(ValueError): locate_new(data, REL)
        with self.assertRaises(ValueError): locate_new(fixture('y = a >= b;', 'missing_type a,b; logic y;'), REL)

    def test_condition_if_ternary_negation_removal(self):
        for before, after in [('if (a) y = b;', 'if (!(a)) y = b;'),
                              ('y = a ? b : y;', 'y = !(a) ? b : y;'),
                              ('if (!a) y=b;', 'if (a) y=b;'),
                              ('if ((!a)) y=b;', 'if ((a)) y=b;')]:
            data = fixture(before)
            t = locate_new(data, COND)
            changed = apply(data,t,approved(COND))
            self.assertEqual(changed,fixture(after))
            self.assertEqual(revert(changed,t),data)

    def test_condition_reset_and_ambiguity_exclusions(self):
        for statement, resets in [('if (!rst_n) y=b;',()), ('if (rst_ni) y=b;',()), ('if (!reset_n) y=b;',()),
                                  ('if (custom_reset || a) y=b;',('custom_reset',)),
                                  ('if(a) y=b; if(b) y=a;',()),
                                  ('if(a) y=b ? a : y;',()), ('if(a &&\n b) y=a;',())]:
            with self.subTest(statement=statement), self.assertRaises(ValueError):
                locate_new(fixture(statement),COND,resets=resets)

    def test_logic_pairs_and_roundtrip(self):
        for before,after in [('&','|'),('|','&'),('&&','||'),('||','&&')]:
            data=fixture(f'y = a {before} b;');t=locate_new(data,LOGIC)
            changed=apply(data,t,approved(LOGIC))
            self.assertEqual(changed,fixture(f'y = a {after} b;'))
            self.assertEqual(revert(changed,t),data)

    def test_logic_reduction_unknown_ambiguous_and_property_exclusions(self):
        for text in ['y = &a;', 'y = |a;', 'y = a & missing;', 'y = a & b | y;',
                     'assert property (a && b);', 'cover property (a || b);',
                     'assert (a && b);', 'y = a &\n b;', '$display("a & b");']:
            with self.subTest(text=text), self.assertRaises(ValueError): locate_new(fixture(text),LOGIC)

    def test_generate_exclusions(self):
        for op,statement in [(COND,'if(a) y=b;'),(LOGIC,'assign y=a & b;')]:
            data=('module m(input a,b, output y);\nfor(genvar i=0;i<1;i++) begin : g\n'
                  +statement+'\nend\nendmodule').encode()
            with self.subTest(op=op), self.assertRaises(ValueError): locate_new(data,op,line=3)

    def test_macros_generated_files_hash_span_and_approval(self):
        for op,statement in [(REL,'y=a>=b;'),(COND,'if(a) y=b;'),(LOGIC,'y=a&b;')]:
            data=fixture(statement);t=locate_new(data,op)
            for path in ['foo_reg_top.sv','foo_reg_pkg.sv']:
                with self.assertRaises(ValueError): locate_new(data,op,path=path)
            for field,value in [('start_byte',0),('end_byte',1),('file_sha256','x'),('after','bad'),('mapper','x')]:
                with self.subTest(op=op,field=field), self.assertRaises(ValueError):
                    apply(data,dict(t,**{field:value}),approved(op))
            with self.assertRaises(ValueError): apply(data+b'\n',t,approved(op))
            with self.assertRaises(ValueError): apply(data,t,dict(approved(op),status='proposed'))
            macro = b'`define BODY '+statement.encode()+b'\n'+fixture('`BODY')
            with self.assertRaises(ValueError): locate_new(macro,op,line=5)

    def test_macro_operand_excluded_even_with_real_operator_token(self):
        data=b'`define A a\n'+fixture('y=`A >= b;')
        with self.assertRaises(ValueError): locate_new(data,REL,line=5)

    def test_pinned_opentitan_fixture(self):
        data=(ROOT/'tests/fixtures/operators/timer_core.sv').read_bytes()
        self.assertEqual(sha(data),'9ebebe1c5517edbba276c25e7594a43ae11588a5627c0e070fe6b927c6944644')
        t=locate_new(data,REL,line=39,path='timer_core.sv')
        self.assertEqual((t['before'],t['column_1based']),('>=',38))
        locate_new(data,COND,line=30,path='timer_core.sv')
        sites=reachable_sites(data,path='timer_core.sv')['sites']
        self.assertEqual([t['line'] for t in sites[REL]],[32,39,45])

    def test_legacy_mapper_provenance_and_crlf(self):
        data=fixture('y = a + b;', 'reg [31:0] a,b,y;').replace(b'\n',b'\r\n')
        t=locate(data,4,'y','b','y = a + b;')
        t['mapper']='pyverilog-1.3.0+checked-single-line-span-v1'
        changed=apply(data,t,approved('unsigned32_root_add_to_sub'))
        self.assertEqual(changed,data.replace(b'a + b',b'a - b'))
        self.assertEqual(revert(changed,t),data)

    def test_registry_approved_and_existing_versions(self):
        # The three new operators were approved by the user on 2026-10-24 (tracker D-09).
        entries=json.loads((ROOT/'rtlprobe/operators.json').read_text())['operators']
        self.assertEqual(len(entries),5)
        for row in entries:
            self.assertEqual(row['version'],'1.0')
            self.assertEqual(row['status'],'approved')
            if row['id'] in NEW_OPERATORS:
                self.assertIn('D-09', row['approval_scope'])
        self.assertEqual(next(r for r in entries if r['id']==COND)['family'],'control')

    def test_candidate_coverage_all_five_operators(self):
        data=fixture("y = a + b;\ny = 32'h12345678;\ny = a >= b;\nif (a) y=b;\ny = a ? b : y;\ny = a & b;")
        sites=reachable_sites(data,path='design.sv')['sites']
        sites={k:[dict(t,path='design.sv') for t in v] for k,v in sites.items()}
        inventory=extract_candidates({'design.sv':data})
        for op,coverage in mapping_coverage(sites,inventory).items():
            self.assertGreater(coverage['reachable'],0,op)
            self.assertEqual(coverage['fraction'],1.0,op)
        self.assertEqual(inventory['rejected'],[])

    def test_candidate_functions_generate_overrides_arrays_and_parse_rejections(self):
        data=b'''module m(input logic [31:0] a,b, output logic y);
function logic f(input logic [31:0] x);
f = x >= b;
endfunction
for(genvar i=0;i<2;i++) begin : g
assign y = a >= b;
end
child #(.N(2)) u[2](.a(a));
endmodule
'''
        inventory=extract_candidates({'x.sv':data})
        self.assertEqual(inventory['rejected'],[])
        self.assertTrue({3,6}.issubset({c['line'] for c in inventory['candidates']}))
        self.assertTrue(any(c['kind']=='FunctionDeclaration' for c in inventory['constructs']))
        self.assertTrue(extract_candidates({'bad.sv':b'module m; `MISSING endmodule'})['rejected'])

    def test_preflight_binds_manifest_resets_and_file(self):
        from rtlprobe.batch import preflight
        data=fixture('if(a) y=b;');t=locate_new(data,COND)
        proposal={'operator':{'id':COND},'target':t,'path':'design.sv'}
        with patch('rtlprobe.batch.pilot.schema'):
            with self.assertRaisesRegex(ValueError,'reset policy'):
                preflight(proposal,{'rtl':['design.sv'],'reset_identifiers':['a']},{})
            with self.assertRaisesRegex(ValueError,'target path'):
                preflight(dict(proposal,path='foo_reg_top.sv'),{'rtl':['foo_reg_top.sv']},{})

    def test_proposal_v2_allows_control_token_deletion(self):
        import jsonschema
        schema=json.loads((ROOT/'rtlprobe/schemas/proposal_v2.json').read_text())
        jsonschema.validate({'after':''}, {'type':'object','properties':{'after':schema['properties']['target']['properties']['after']}})
        self.assertIn('control',schema['properties']['family']['enum'])

    def test_gate_diff_and_read_only_temporary_root(self):
        spec=importlib.util.spec_from_file_location('operator_regression',ROOT/'scripts/operator_regression.py')
        gate_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate_module)
        data=fixture('y = a + b;','reg [31:0] a,b,y;')
        target=locate(data,4,'y','b','y = a + b;')
        proposal={'path':'design.v','target':target,'operator':approved('unsigned32_root_add_to_sub')}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'data/manifests').mkdir(parents=True);out=root/'case'
            (out/'rtl/original').mkdir(parents=True);(out/'rtl/original/design.v').write_bytes(data)
            (root/'data/manifests/a.json').write_text(json.dumps({'state':'accepted_core','case_id':'a','case_path':'case'}))
            changed=apply(data,target,proposal['operator'])
            derived=b''.join(difflib.diff_bytes(difflib.unified_diff,data.splitlines(True),changed.splitlines(True),fromfile=b'a/design.v',tofile=b'b/design.v'))
            (out/'mutation.patch').write_bytes(derived)
            with patch.object(gate_module,'verify_index',return_value={'proposal':proposal}):
                snapshot={str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()}
                self.assertEqual(gate_module.gate(root)['matches'],1)
                self.assertEqual(snapshot,{str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()})
                (out/'mutation.patch').write_bytes(b'wrong patch\n')
                mismatch=gate_module.gate(root)
                self.assertEqual(mismatch['mismatches'],1)
                self.assertIn('sealed.patch',mismatch['cases'][0]['diff'])

    def test_comment_bytes_and_hex_case_preserved(self):
        data=fixture('y = a >= b; // comparison comment')
        t=locate_new(data,REL);changed=apply(data,t,approved(REL))
        self.assertEqual(changed,fixture('y = a > b; // comparison comment'))
        data=fixture("y = 32'hAbCdEF0F;",'reg [31:0] y;')
        t=locate_constant(data,4,'y',"y = 32'hAbCdEF0F;")
        self.assertEqual(apply(data,t,approved('literal_lsb_flip32')),data.replace(b'AbCdEF0F',b'AbCdEF0E'))

    def test_macro_rejection_does_not_hide_other_candidate_sites(self):
        data=b'`define COMP a >= b\n'+fixture('y = `COMP;\ny = a > b;')
        sites=reachable_sites(data,path='x.sv')['sites']
        self.assertEqual([s['line'] for s in sites[REL]],[6])
        inventory=extract_candidates({'x.sv':data})
        self.assertTrue(inventory['rejected'])
        self.assertTrue(any(c['line']==6 for c in inventory['candidates']))

    def test_approved_operator_multiline_statements_rejected(self):
        for data in [b'module m;\nlocalparam P =\n63;\nendmodule',
                     b'module m;\nlocalparam P = 63\n;\nendmodule']:
            with self.assertRaises(ValueError): locate_constant(data,2,'P',data.decode().splitlines()[1])
        data=fixture('y = a + b\n;', 'reg [31:0] a,b,y;')
        with self.assertRaises(ValueError): locate(data,4,'y','b','y = a + b')
