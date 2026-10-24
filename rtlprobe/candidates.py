"""Source-only candidate universe, independent of mutation records and registry.

Syntax coverage is separate from hierarchy / dependency elaboration. Functions,
parameter overrides, generate blocks and instance arrays remain in the syntax
inventory; this module makes no claim to elaborate their dependency graph.
"""
from .sv_frontend import Source, ancestors, identifier, kind, walk

ASSIGNMENTS = {'AssignmentExpression', 'NonblockingAssignmentExpression'}
BINARY = {'GreaterThanExpression', 'GreaterThanEqualExpression', 'LessThanExpression',
          'LessThanEqualExpression', 'EqualityExpression', 'InequalityExpression',
          'BinaryAndExpression', 'BinaryOrExpression', 'LogicalAndExpression', 'LogicalOrExpression'}


def _names(node):
    return {identifier(n) for n in walk(node) if kind(n) == 'IdentifierName'}


def extract_candidates(sources):
    """One candidate per file/module/line, with exact constituent token spans.

    This rule includes assignments, parameters, if/ternary conditions and binary
    comparison / logic expressions. It is a proposed rule, not a protocol freeze.
    Files that fail parsing are returned as explicit rejections, never empty sets.
    """
    rows, rejected, constructs = {}, [], []
    for path, text in sorted(sources.items()):
        data = text.encode('ascii') if isinstance(text, str) else text
        try:
            source = Source(data)
        except ValueError as exc:
            rejected.append({'path': path, 'reason': str(exc)})
            continue
        for node in source.nodes:
            try:
                k = kind(node)
                parents = list(ancestors(node))
                if k in {'FunctionDeclaration', 'LoopGenerate', 'IfGenerate', 'CaseGenerate',
                         'GenerateRegion', 'HierarchyInstantiation'}:
                    constructs.append({'path': path, 'line': source.line(node), 'kind': k,
                                       'dependency_elaboration': 'not provided by syntax extractor'})
                module = next((p.header.name.valueText for p in parents if kind(p) == 'ModuleDeclaration'), None)
                if module is None:
                    continue
                selected, spans, outputs = node, [], set()
                if k in ASSIGNMENTS:
                    outputs = _names(node.left)
                    spans.append(source.span(node))
                    if kind(node.right) in {'IntegerLiteralExpression', 'IntegerVectorExpression'}:
                        spans.append(source.span(node.right))
                    if kind(node.right) == 'AddExpression':
                        spans.append(source.token_span(node.right.operatorToken))
                elif k == 'Declarator' and kind(node.parent) == 'ParameterDeclaration' and node.initializer is not None:
                    outputs = {node.name.valueText}
                    spans.append(source.span(node.initializer.expr))
                elif k in {'ConditionalStatement', 'ConditionalExpression'}:
                    patterns = list(node.predicate.conditions)
                    if len(patterns) != 1 or patterns[0].matchesClause is not None:
                        rejected.append({'path': path, 'line': source.line(node), 'reason': 'Pattern condition unsupported'})
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
                elif k in BINARY:
                    spans.append(source.token_span(node.operatorToken))
                else:
                    continue
                # A nested expression affects its containing assignment's outputs.
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
                    'lhs': [], 'dependencies': [], 'text': data.decode('ascii').splitlines()[line - 1].strip()})
                row['syntax_kinds'] = sorted(set(row['syntax_kinds']) | {k})
                row['lhs'] = sorted(set(row['lhs']) | outputs)
                row['dependencies'] = sorted(set(row['dependencies']) | _names(selected))
                for start, end in spans:
                    span = {'start_byte': start, 'end_byte': end,
                            'line': data[:start].count(b'\n') + 1,
                            'column_1based': start - data.rfind(b'\n', 0, start)}
                    if span not in row['site_spans']:
                        row['site_spans'].append(span)
            except ValueError as exc:
                rejected.append({'path': path, 'line': source.line(node),
                                 'kind': kind(node), 'reason': str(exc)})
    return {'candidates': list(rows.values()), 'rejected': rejected, 'constructs': constructs,
            'rule': 'source-syntax-conditions-v1',
            'limitations': ['source coordinates only; no elaboration or function dependency model',
                            'macro-derived sites are not candidates',
                            'not a frozen study candidate rule']}


def mapping_coverage(sites, inventory):
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
