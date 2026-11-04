"""Source-only contracts and curator recall, without hardware runs."""
import copy
import unittest
from unittest.mock import patch
from rtlprobe.candidates import RULE_ID, audit_recall, extract_candidates, mapping_coverage, rule_contract, validate_inventory

SOURCE=b'''module m(input logic rst,a,b, output logic y);
localparam P = 32'h00000001;
logic initialized = 1'b0;
always_comb begin
  if (rst) y = 1'b0;
  else if (a >= b) y = a & b;
  y = a ? b : y;
end
endmodule
'''

class CandidateTests(unittest.TestCase):
    def test_version_identity_and_hashes_are_deterministic(self):
        a=extract_candidates({'x.sv':SOURCE,'empty.sv':b'module empty; endmodule\n'})
        b=extract_candidates({'empty.sv':'module empty; endmodule\n','x.sv':SOURCE})
        self.assertEqual(a,b);self.assertEqual(a['rule_id'],RULE_ID)
        self.assertEqual(a['contract'],rule_contract());self.assertEqual(a['status'],'complete')
        self.assertEqual(a['file_status']['empty.sv']['candidate_count'],0)
        self.assertTrue(all(c['source_sha256']==a['source_hashes'][c['path']] for c in a['candidates']))
        self.assertEqual(len({c['candidate_id'] for c in a['candidates']}),len(a['candidates']))
        self.assertNotEqual(a['inventory_id'],extract_candidates({'x.sv':SOURCE+b'// change\n'})['inventory_id'])
    def test_conditions_initializers_and_constituent_spans(self):
        rows={c['line']:c for c in extract_candidates({'x.sv':SOURCE})['candidates']}
        self.assertTrue({2,3,5,6,7}<=set(rows));self.assertEqual(rows[2]['lhs'],['P'])
        self.assertIn('ConditionalStatement',rows[5]['syntax_kinds'])
        self.assertIn('ConditionalExpression',rows[7]['syntax_kinds'])
        for row in rows.values():
            self.assertEqual(row['site_spans'],sorted(row['site_spans'],key=lambda s:(s['start_byte'],s['end_byte'])))
            for s in row['site_spans']:
                self.assertLess(s['start_byte'],s['end_byte'])
                self.assertEqual(SOURCE[:s['start_byte']].count(b'\n')+1,s['line'])
                self.assertEqual(SOURCE[:s['end_byte']].count(b'\n')+1,s['end_line'])
        self.assertEqual(len([c for c in rows.values() if c['line']==6]),1)
    def test_crlf_byte_coordinates(self):
        data=SOURCE.replace(b'\n',b'\r\n')
        row=next(c for c in extract_candidates({'x.sv':data})['candidates'] if c['line']==2)
        span=row['site_spans'][0]
        self.assertEqual(data[span['start_byte']:span['end_byte']],b"32'h00000001")
    def test_parse_failure_is_unknown_not_zero_and_other_files_survive(self):
        inv=extract_candidates({'good.sv':SOURCE,'bad.sv':b'module bad; `MISSING endmodule'})
        self.assertEqual(inv['status'],'partial');self.assertTrue(inv['rejected']);self.assertTrue(inv['candidates'])
        self.assertEqual(inv['file_status']['bad.sv']['status'],'rejected')
        self.assertIsNone(inv['file_status']['bad.sv']['candidate_count'])
        self.assertEqual(inv['missingness']['dependency_elaboration'],'not_provided')
    def test_macro_failure_preserves_independent_sites(self):
        data=b'`define COMP a >= b\nmodule m(input logic a,b,output logic y);\nalways_comb begin\ny = `COMP;\ny = a > b;\nend\nendmodule\n'
        inv=extract_candidates({'x.sv':data})
        self.assertEqual(inv['status'],'partial');self.assertTrue(inv['rejected'])
        self.assertTrue(any(c['line']==5 for c in inv['candidates']))
    def test_dependency_unsupported_is_separate_from_syntax_coverage(self):
        data=b'''module m(input logic a,b, output logic y);
function logic f(input logic x);
f=x>=b;
endfunction
for(genvar i=0;i<2;i++) begin : g
assign y=a>=b;
end
child #(.N(2)) u[2](.a(a));
endmodule
'''
        inv=extract_candidates({'x.sv':data})
        self.assertEqual(inv['status'],'complete');self.assertTrue({3,6}<={c['line'] for c in inv['candidates']})
        self.assertTrue(any(c['kind']=='FunctionDeclaration' for c in inv['constructs']))
        self.assertTrue(any(c['kind']=='HierarchyInstantiation' for c in inv['constructs']))
        self.assertEqual(inv['missingness']['signal_time_mapping'],'not_provided')
    def test_metadata_does_not_influence_extraction_and_audits_do_not_filter(self):
        with patch('builtins.open',side_effect=AssertionError('must not read metadata')):
            inv=extract_candidates({'x.sv':SOURCE})
        before=copy.deepcopy(inv)
        audit_recall(inv,[{'path':'x.sv','line':6}],match='line',retained_candidate_ids=[])
        mapping_coverage({},inv);self.assertEqual(inv,before)
        with self.assertRaises(ValueError):extract_candidates({'x.sv':{'source':SOURCE,'label':6}})
    def test_line_and_span_recall_are_explicit(self):
        inv=extract_candidates({'x.sv':SOURCE});row=next(c for c in inv['candidates'] if c['line']==6)
        span=row['site_spans'][0]
        line=audit_recall(inv,[{'path':'x.sv','line':6}],match='line')
        exact=audit_recall(inv,[{'path':'x.sv','start_byte':span['start_byte'],'end_byte':span['end_byte']}],match='span')
        self.assertEqual(line['recall'],1);self.assertEqual(exact['recall'],1);self.assertEqual(line['tie_policy'],'not_selected')
        with self.assertRaises(TypeError):audit_recall(inv,[{'path':'x.sv','line':6}])
        with self.assertRaises(ValueError):audit_recall(inv,[],match='invented')
    def test_filtering_and_unmapped_truths_remain_misses(self):
        inv=extract_candidates({'x.sv':SOURCE})
        audit=audit_recall(inv,[{'path':'x.sv','line':6},{'path':'x.sv','line':99}],match='line',retained_candidate_ids=[])
        self.assertEqual((audit['true_sites'],audit['mapped'],audit['missed'],audit['recall']),(2,0,2,0))
        self.assertEqual([r['reason'] for r in audit['sites']],['filtered_from_universe','not_in_universe'])
        self.assertEqual(audit['inventory_id'],inv['inventory_id']);self.assertEqual(audit['access'],'curator_only')
        self.assertIsNone(audit_recall(inv,[],match='line')['recall'])
        with self.assertRaises(ValueError):audit_recall(inv,[],match='line',retained_candidate_ids=['invented'])
    def test_nonascii_and_unsafe_paths_explicit(self):
        inv=extract_candidates({'x.sv':'module m; // café\nendmodule\n'})
        self.assertEqual(inv['status'],'rejected');self.assertIsNone(inv['file_status']['x.sv']['candidate_count'])
        for path in ['/absolute.sv','../parent.sv','a/../x.sv','./x.sv','a\\x.sv']:
            with self.subTest(path=path),self.assertRaises(ValueError):extract_candidates({path:SOURCE})
    def test_assertion_context_is_explicitly_excluded(self):
        data=b'module m(input logic clk,a,b);\nassert property (@(posedge clk) a >= b);\nendmodule\n'
        inv=extract_candidates({'x.sv':data})
        self.assertEqual(inv['status'],'complete')
        self.assertEqual(inv['candidates'],[])
        self.assertTrue(any(r['reason_code']=='assertion_property_sequence_context' for r in inv['excluded']))
    def test_inventory_integrity_and_reextraction(self):
        inv=extract_candidates({'x.sv':SOURCE})
        self.assertEqual(validate_inventory(inv,{'x.sv':SOURCE}),inv)
        changed=copy.deepcopy(inv);changed['candidates'][0]['line']+=1
        with self.assertRaisesRegex(ValueError,'identity mismatch'):validate_inventory(changed)
        with self.assertRaisesRegex(ValueError,'re-extraction'):validate_inventory(inv,{'x.sv':SOURCE+b'// changed\n'})
        with self.assertRaisesRegex(ValueError,'another source'):audit_recall(inv,[{'path':'x.sv','line':6,'source_sha256':'0'*64}],match='line')
    def test_empty_input_has_explicit_status(self):
        inv=extract_candidates({});self.assertEqual(inv['status'],'empty')
        self.assertEqual(inv['coverage']['input_files'],0);self.assertEqual(inv['candidates'],[])

if __name__=='__main__':unittest.main()
