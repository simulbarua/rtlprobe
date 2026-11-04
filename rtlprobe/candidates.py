"""Versioned source-only candidate inventory; curator recall auditing is separate.

Extraction takes only supplied source bytes. No registry, mutation record, label,
trace, model result, or condition controls which candidates are emitted.
"""
import hashlib
import json
from pathlib import PurePosixPath

from .sv_frontend import Source, ancestors, identifier, kind, walk

RULE_ID = 'source-syntax-line-v2'
SCHEMA_VERSION = 'candidate-inventory-1'
ASSIGNMENTS = {'AssignmentExpression', 'NonblockingAssignmentExpression'}
BINARY = {'GreaterThanExpression', 'GreaterThanEqualExpression', 'LessThanExpression',
          'LessThanEqualExpression', 'EqualityExpression', 'InequalityExpression',
          'BinaryAndExpression', 'BinaryOrExpression', 'LogicalAndExpression', 'LogicalOrExpression'}
CONSTRUCTS = {'FunctionDeclaration', 'LoopGenerate', 'IfGenerate', 'CaseGenerate',
              'GenerateRegion', 'HierarchyInstantiation'}


def _identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _names(node):
    return {identifier(n) for n in walk(node) if kind(n) == 'IdentifierName'}


def _path(value):
    if not isinstance(value, str):
        raise ValueError('Source path must be a canonical relative string')
    path = PurePosixPath(value)
    if not path.parts or path.is_absolute() or '..' in path.parts or str(path) != value or '\\' in value:
        raise ValueError('Source path must be canonical and repository-relative')
    return value


def _line(source, node):
    try:
        return source.line(node)
    except ValueError:
        return None


def _span(data, start, end):
    return {'start_byte': start, 'end_byte': end,
            'line': data[:start].count(b'\n') + 1,
            'column_1based': start - data.rfind(b'\n', 0, start),
            'end_line': data[:end].count(b'\n') + 1,
            'end_column_1based': end - data.rfind(b'\n', 0, end)}


def rule_contract():
    """Implementation contract; returning it does not adopt a study protocol."""
    return {'rule_id': RULE_ID, 'candidate_unit': 'one row per path/module/anchor line',
            'coordinates': 'one-based lines/columns; zero-based half-open byte spans; ASCII sources',
            'included': ['simple blocking (=) and nonblocking (<=) assignments', 'initialized declarators',
                         'simple if and ternary predicates, including reset conditions',
                         'binary comparison and AND/OR expressions'],
            'excluded': ['declarations without initializers', 'compound assignments and standalone calls', 'non-module scopes',
                         'assertion/property/sequence contexts', 'macro-derived or unmappable spans',
                         'pattern/multiple predicates', 'files failing standalone syntax parsing'],
            'grouping': 'same-line constructs in one module merge constituent spans and source names',
            'selection': 'all emitted rows retained identically across conditions; no evidence-dependent filtering',
            'scoring_options': {'line': 'exact path and candidate anchor line (module optional in supplied truth)',
                                'span': 'exact constituent byte span identity (module optional in supplied truth)'},
            'filter_audit': 'omitted true sites count as misses; retain the original universe identity',
            'protocol_status': 'candidate/scoring/tie policy requires explicit adoption and study freeze'}


def extract_candidates(sources):
    """Enumerate deterministic source locations without consulting outcome or labels.

    A syntactically complete inventory covers this declared rule, not every RTL
    construct or dependency mapping. Parse and source-coordinate failures are
    explicit, so an unsupported file cannot masquerade as a measured zero count.
    """
    if not isinstance(sources, dict):
        raise ValueError('Sources must map relative paths to source text or bytes')
    rows, rejected, constructs, excluded, source_hashes, file_status = {}, [], [], [], {}, {}
    for path in sources:
        _path(path)
    for path, text in sorted(sources.items()):
        if not isinstance(text, (str, bytes)):
            raise ValueError('Source values must be text or bytes, without metadata')
        data = text.encode('utf-8') if isinstance(text, str) else text
        source_hashes[path] = hashlib.sha256(data).hexdigest()
        first_rejection = len(rejected)
        try:
            data.decode('ascii')
            source = Source(data)
        except (ValueError, UnicodeError) as exc:
            rejected.append({'path': path, 'reason_code': 'source_parse_or_encoding', 'reason': str(exc)})
            file_status[path] = {'status': 'rejected', 'candidate_count': None,
                                 'missing_reason': 'source_parse_or_encoding'}
            continue
        for node in source.nodes:
            k = kind(node)
            parents = list(ancestors(node))
            eligible = (k in ASSIGNMENTS or k in BINARY or k in {'ConditionalStatement', 'ConditionalExpression'}
                        or (k == 'Declarator' and node.initializer is not None))
            if not eligible and k not in CONSTRUCTS:
                continue
            try:
                if k in CONSTRUCTS:
                    constructs.append({'path': path, 'line': source.line(node), 'kind': k,
                                       'dependency_elaboration': 'not provided by syntax extractor'})
                module = next((p.header.name.valueText for p in parents if kind(p) == 'ModuleDeclaration'), None)
                if not eligible:
                    continue
                if module is None:
                    excluded.append({'path': path, 'line': _line(source, node), 'kind': k,
                                     'reason_code': 'non_module_scope'})
                    continue
                if any('Assertion' in kind(p) or kind(p) in {'PropertyDeclaration', 'SequenceDeclaration'} for p in parents):
                    excluded.append({'path': path, 'line': _line(source, node), 'kind': k,
                                     'reason_code': 'assertion_property_sequence_context'})
                    continue
                selected, spans, outputs = node, [], set()
                if k in ASSIGNMENTS:
                    outputs = _names(node.left)
                    spans.append(source.span(node))
                    if kind(node.right) in {'IntegerLiteralExpression', 'IntegerVectorExpression'}:
                        spans.append(source.span(node.right))
                    if kind(node.right) == 'AddExpression':
                        spans.append(source.token_span(node.right.operatorToken))
                elif k == 'Declarator':
                    outputs = {node.name.valueText}
                    spans.append(source.span(node.initializer.expr))
                elif k in {'ConditionalStatement', 'ConditionalExpression'}:
                    patterns = list(node.predicate.conditions)
                    if len(patterns) != 1 or patterns[0].matchesClause is not None:
                        rejected.append({'path': path, 'line': _line(source, node), 'kind': k,
                                         'reason_code': 'unsupported_predicate', 'reason': 'Pattern or multiple condition unsupported'})
                        continue
                    selected = patterns[0].expr
                    spans.append(source.span(selected))
                    outer = selected
                    while kind(outer) == 'ParenthesizedExpression':
                        outer = outer.expression
                    if kind(outer) == 'UnaryLogicalNotExpression':
                        spans.append(source.token_span(outer.operatorToken))
                    for n in walk(node):
                        if kind(n) in ASSIGNMENTS:
                            outputs.update(_names(n.left))
                else:
                    spans.append(source.token_span(node.operatorToken))
                for parent in parents:
                    if kind(parent) in ASSIGNMENTS:
                        outputs.update(_names(parent.left))
                        break
                    if kind(parent) == 'ConditionalStatement':
                        for n in walk(parent):
                            if kind(n) in ASSIGNMENTS:
                                outputs.update(_names(n.left))
                        break
                line = source.line(selected)
                key = path, module, line
                row = rows.setdefault(key, {'path': path, 'module': module, 'line': line,
                    'kind': 'source_syntax', 'syntax_kinds': [], 'site_spans': [],
                    'lhs': [], 'dependencies': [], 'text': data.decode('ascii').splitlines()[line - 1].strip(),
                    'source_sha256': source_hashes[path], 'mapping_status': 'source_mapped'})
                row['syntax_kinds'] = sorted(set(row['syntax_kinds']) | {k})
                row['lhs'] = sorted(set(row['lhs']) | outputs)
                row['dependencies'] = sorted(set(row['dependencies']) | _names(selected))
                for start, end in spans:
                    span = _span(data, start, end)
                    if span not in row['site_spans']:
                        row['site_spans'].append(span)
            except ValueError as exc:
                rejected.append({'path': path, 'line': _line(source, node), 'kind': k,
                                 'reason_code': 'unmapped_source_span', 'reason': str(exc)})
        file_status[path] = {'status': 'partial' if len(rejected) > first_rejection else 'complete',
                             'candidate_count': sum(k[0] == path for k in rows),
                             'missing_reason': 'unmapped_source_constructs' if len(rejected) > first_rejection else None}
    candidates = []
    for key, row in sorted(rows.items()):
        row['site_spans'].sort(key=lambda s: (s['start_byte'], s['end_byte']))
        row['candidate_id'] = 'candidate-'+_identity({'rule_id': RULE_ID, 'path': row['path'],
            'module': row['module'], 'line': row['line'], 'source_sha256': row['source_sha256']})
        candidates.append(row)
    # Stable deduplication preserves explicit diagnostics without AST-repeat noise.
    dedup = lambda values: [json.loads(v) for v in sorted({json.dumps(x, sort_keys=True) for x in values})]
    rejected, constructs, excluded = map(dedup, (rejected, constructs, excluded))
    statuses = [v['status'] for v in file_status.values()]
    status = ('empty' if not statuses else 'complete' if all(s == 'complete' for s in statuses)
              else 'rejected' if all(s == 'rejected' for s in statuses) else 'partial')
    result = {'schema_version': SCHEMA_VERSION, 'rule': RULE_ID, 'rule_id': RULE_ID,
              'policy_status': 'implementation_available_protocol_adoption_pending',
              'contract': rule_contract(), 'source_hashes': source_hashes, 'candidates': candidates,
              'rejected': rejected, 'constructs': constructs, 'excluded': excluded,
              'file_status': file_status, 'status': status,
              'coverage': {'input_files': len(sources), 'complete_files': statuses.count('complete'),
                           'partial_files': statuses.count('partial'), 'rejected_files': statuses.count('rejected'),
                           'candidate_count': len(candidates), 'rejected_constructs': len(rejected)},
              'missingness': {'source_candidates': 'present' if status == 'complete' else status,
                              'dependency_elaboration': 'not_provided', 'signal_time_mapping': 'not_provided'},
              'limitations': ['standalone source syntax; no include/package/elaboration context',
                             'no hierarchy or function dependency elaboration',
                             'macro-derived sites are reported as unmapped',
                             'implemented rule is not an adopted/frozen study scoring or tie policy']}
    result['inventory_id'] = 'inventory-'+_identity(result)
    return result



def validate_inventory(inventory, sources=None):
    """Verify inventory identity; optional sources require exact re-extraction.

    Use the complete inventory here, before producing an allowlisted public
    projection. This checks integrity/compatibility, not protocol adoption.
    """
    if (not isinstance(inventory, dict) or inventory.get('schema_version') != SCHEMA_VERSION
            or inventory.get('rule_id') != RULE_ID or inventory.get('rule') != RULE_ID):
        raise ValueError('Unsupported candidate inventory contract')
    content = {k: v for k, v in inventory.items() if k != 'inventory_id'}
    if inventory.get('inventory_id') != 'inventory-'+_identity(content):
        raise ValueError('Candidate inventory identity mismatch')
    if inventory.get('contract') != rule_contract():
        raise ValueError('Candidate rule contract mismatch')
    ids = set()
    for row in inventory['candidates']:
        path = _path(row['path'])
        if row['source_sha256'] != inventory['source_hashes'].get(path):
            raise ValueError('Candidate source binding mismatch')
        expected = 'candidate-'+_identity({'rule_id': RULE_ID, 'path': path, 'module': row['module'],
            'line': row['line'], 'source_sha256': row['source_sha256']})
        if row['candidate_id'] != expected or expected in ids:
            raise ValueError('Candidate identity mismatch or duplicate')
        ids.add(expected)
        if type(row['line']) is not int or row['line'] < 1:
            raise ValueError('Candidate anchor line must be positive')
        for span in row['site_spans']:
            if (any(type(span.get(k)) is not int for k in ('start_byte', 'end_byte', 'line', 'column_1based', 'end_line', 'end_column_1based'))
                    or not 0 <= span['start_byte'] < span['end_byte']
                    or min(span['line'], span['column_1based'], span['end_line'], span['end_column_1based']) < 1):
                raise ValueError('Invalid candidate source span')
    if sources is not None and inventory != extract_candidates(sources):
        raise ValueError('Candidate inventory differs from source re-extraction')
    return inventory


def mapping_coverage(sites, inventory):
    """Curator operator-site audit; never use the result to select the universe."""
    spans = {(c['path'], s['line'], s['column_1based'], s['start_byte'], s['end_byte'])
             for c in inventory['candidates'] for s in c['site_spans']}
    result = {}
    for op, targets in sites.items():
        missing = [t for t in targets if (t['path'], t['line'], t['column_1based'],
                   t['start_byte'], t['end_byte']) not in spans]
        total = len(targets)
        result[op] = {'reachable': total, 'mapped': total - len(missing),
                      'fraction': (total - len(missing)) / total if total else None,
                      'missing': missing}
    return result


def audit_recall(inventory, true_sites, *, match, retained_candidate_ids=None):
    """Curator-only exact line/span recall, with an explicit scoring choice.

    This function does not rank candidates, resolve ties, alter the inventory,
    or adopt a protocol. Its true-site records and returned audit must never be
    included in inference exports. Filtering omissions remain denominator misses.
    """
    if match not in {'line', 'span'}:
        raise ValueError('Choose explicit line or span recall semantics')
    candidates = inventory['candidates']
    ids = {c['candidate_id'] for c in candidates}
    retained = ids if retained_candidate_ids is None else set(retained_candidate_ids)
    if retained - ids:
        raise ValueError('Retained candidate IDs must belong to the original universe')
    rows = []
    for truth in true_sites:
        path = _path(truth['path'])
        if ('source_sha256' in truth and truth['source_sha256'] != inventory['source_hashes'].get(path)):
            raise ValueError('True-site coordinates belong to another source snapshot')
        if match == 'line' and (type(truth.get('line')) is not int or truth['line'] < 1):
            raise ValueError('Line recall requires a positive line coordinate')
        if match == 'span' and (type(truth.get('start_byte')) is not int or type(truth.get('end_byte')) is not int
                               or not 0 <= truth['start_byte'] < truth['end_byte']):
            raise ValueError('Span recall requires a nonempty half-open byte span')
        matches = []
        for c in candidates:
            if c['path'] != path or ('module' in truth and truth['module'] != c['module']):
                continue
            covered = (c['line'] == truth['line'] if match == 'line' else any(
                s['start_byte'] == truth['start_byte'] and s['end_byte'] == truth['end_byte'] for s in c['site_spans']))
            if covered:
                matches.append(c['candidate_id'])
        available = sorted(set(matches) & retained)
        rows.append({'true_site': dict(truth), 'universe_candidate_ids': sorted(matches),
                     'retained_candidate_ids': available, 'mapped': bool(available),
                     'reason': None if available else 'filtered_from_universe' if matches else 'not_in_universe'})
    mapped = sum(r['mapped'] for r in rows)
    total = len(rows)
    return {'schema_version': 'candidate-recall-audit-1', 'access': 'curator_only',
            'inventory_id': inventory['inventory_id'], 'rule_id': inventory['rule_id'],
            'match': match, 'true_sites': total, 'mapped': mapped, 'missed': total-mapped,
            'recall': mapped/total if total else None, 'candidate_count': len(candidates),
            'retained_candidate_count': len(retained), 'omitted_true_sites_scored_as_misses': True,
            'tie_policy': 'not_selected', 'sites': rows}
