"""AST-located single edits with exact source hash and token-span validation."""
import hashlib
import re
from pathlib import PurePosixPath

from .sv_frontend import Source, ancestors, identifier, kind, walk

MAPPER = 'pyslang-12.0.0+checked-span-v1'
LEGACY_MAPPERS = {
    'unsigned32_root_add_to_sub': 'pyverilog-1.3.0+checked-single-line-span-v1',
    'literal_lsb_flip32': 'pyverilog-1.3.0+checked-literal-span-v1',
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def safe_path(value):
    path = PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts or str(path) != value or not path.parts:
        raise ValueError('Unsafe or noncanonical repository-relative path')
    return path


def parse(data):
    return Source(data).tree.root


def _statement(source, line, expected, allow_comments=False):
    lines = source.data.splitlines(keepends=True)
    if not 1 <= line <= len(lines):
        raise ValueError('Invalid source line')
    raw = lines[line - 1]
    if raw.strip().decode('ascii') != expected or (not allow_comments and (b'//' in raw or b'/*' in raw or b'`' in raw)):
        raise ValueError('Source statement does not match planned text')


def _record(source, line, expected, start, end, after, **extra):
    return dict(line=line, column_1based=start - source.data.rfind(b'\n', 0, start),
                start_byte=start, end_byte=end, before=source.data[start:end].decode('ascii'),
                after=after, statement=expected, file_sha256=sha(source.data), mapper=MAPPER, **extra)


def _decl32(source, name, reg_only=False):
    decls = [n for n in source.nodes if kind(n) == 'Declarator' and n.name.valueText == name]
    if len(decls) != 1:
        raise ValueError('Ambiguous or missing declaration: ' + name)
    decl = decls[0].parent
    allowed = {'DataDeclaration'} if reg_only else {'DataDeclaration', 'NetDeclaration'}
    if kind(decl) == 'ImplicitAnsiPort':
        dtype = decl.header.dataType
    elif kind(decl) in allowed:
        dtype = decl.type
    else:
        raise ValueError('Expected register/wire declaration: ' + name)
    # Preserve the original approved operator domain (explicit unsigned [31:0]).
    if (kind(dtype) not in {'RegType', 'LogicType', 'ImplicitType'}
            or (reg_only and kind(dtype) not in {'RegType', 'LogicType'})
            or str(dtype.signing).strip() == 'signed' or len(dtype.dimensions) != 1):
        raise ValueError('Expected unsigned 32-bit declaration: ' + name)
    dim = dtype.dimensions[0].specifier
    if kind(dim) != 'RangeDimensionSpecifier':
        raise ValueError('Expected explicit packed range')
    sel = dim.selector
    if kind(sel) != 'SimpleRangeSelect' or source.text(sel.left) != '31' or source.text(sel.right) != '0':
        raise ValueError('Expected unsigned 32-bit declaration: ' + name)


def _assignment(source, line, lhs):
    matches = [n for n in source.nodes if kind(n) == 'AssignmentExpression'
               and source.line(n) == line and identifier(n.left) == lhs
               and kind(n.parent) == 'ExpressionStatement']
    if len(matches) != 1:
        raise ValueError('Expected exactly one AST assignment at declared site')
    source.single_line(matches[0].parent)
    return matches[0]


def locate(data, line, lhs, rhs_tail, expected_text):
    source = Source(data)
    _statement(source, line, expected_text)
    expr = _assignment(source, line, lhs).right
    if kind(expr) != 'AddExpression' or identifier(expr.right) != rhs_tail:
        raise ValueError('Site is not the supported root addition')
    if any(kind(n) not in {'AddExpression', 'IdentifierName'} for n in walk(expr)):
        raise ValueError('Only unsigned identifier-addition chains are supported')
    names = {identifier(n) for n in walk(expr) if kind(n) == 'IdentifierName'} | {lhs}
    for name in names:
        _decl32(source, name)
    start, end = source.token_span(expr.operatorToken)
    return _record(source, line, expected_text, start, end, '-', lhs=lhs, rhs_tail=rhs_tail)


def _literal(source, line, lhs):
    if sum(kind(n) == 'ModuleDeclaration' for n in source.nodes) != 1:
        raise ValueError('Constant mapper supports exactly one module')
    matches = []
    for node in source.nodes:
        if kind(node) == 'Declarator' and node.name.valueText == lhs:
            parent = node.parent
            if (kind(parent) == 'ParameterDeclaration' and parent.keyword.valueText == 'localparam'
                    and source.line(node) == line and node.initializer is not None):
                source.single_line(parent.parent if kind(parent.parent) == 'ParameterDeclarationStatement' else parent)
                matches.append((node.initializer.expr, 'localparam'))
        elif (kind(node) == 'AssignmentExpression' and identifier(node.left) == lhs
              and source.line(node) == line and kind(node.parent) == 'ExpressionStatement'):
            source.single_line(node.parent)
            _decl32(source, lhs, reg_only=True)
            matches.append((node.right, 'assignment'))
    if len(matches) != 1 or kind(matches[0][0]) not in {'IntegerLiteralExpression', 'IntegerVectorExpression'}:
        raise ValueError('Expected exactly one constant RHS at the declared AST site')
    return matches[0]


def literal_assignment(data, line, lhs):
    source = Source(data)
    node, construct = _literal(source, line, lhs)
    return source.text(node), construct


def flipped_literal(value):
    if re.fullmatch(r"32'h[0-9a-fA-F]{8}", value):
        last = format(int(value[-1], 16) ^ 1, 'x')
        return value[:-1] + (last.upper() if value[-1].isupper() else last)
    if re.fullmatch(r'0|[1-9][0-9]*', value) and int(value) < 2**31:
        return str(int(value) ^ 1)
    raise ValueError('Only 32-bit hex or nonnegative 32-bit-range unsized decimal literals supported')


def locate_constant(data, line, lhs, expected_text):
    source = Source(data)
    _statement(source, line, expected_text)
    node, construct = _literal(source, line, lhs)
    start, end = source.single_line(node)
    return _record(source, line, expected_text, start, end, flipped_literal(source.text(node)),
                   lhs=lhs, rhs_tail=None, construct=construct)


def apply(data, target, registry):
    op = registry['id']
    if op in NEW_OPERATORS:
        return _apply_new(data, target, registry)
    if op not in LEGACY_MAPPERS or registry['version'] != '1.0' or registry['status'] != 'approved':
        raise ValueError('Operator is not an approved supported version')
    if sha(data) != target['file_sha256']:
        raise ValueError('Source hash does not match mutation proposal')
    if op == 'literal_lsb_flip32':
        actual = locate_constant(data, target['line'], target['lhs'], target['statement'])
    else:
        actual = locate(data, target['line'], target['lhs'], target['rhs_tail'], target['statement'])
    # Historical sealed proposals keep their mapper provenance. Every other field
    # must still match a fresh pyslang derivation, including the exact byte span.
    if target.get('mapper') == LEGACY_MAPPERS[op]:
        actual['mapper'] = target['mapper']
    if actual != target:
        raise ValueError('Proposal coordinates or preconditions do not match source')
    changed = data[:target['start_byte']] + target['after'].encode('ascii') + data[target['end_byte']:]
    post = Source(changed)
    if op == 'literal_lsb_flip32':
        node, construct = _literal(post, target['line'], target['lhs'])
        if post.text(node) != target['after'] or construct != target['construct']:
            raise ValueError('Post-mutation constant AST mismatch')
    elif kind(_assignment(post, target['line'], target['lhs']).right) != 'SubtractExpression':
        raise ValueError('Post-mutation AST does not contain the intended subtraction')
    return changed


def apply_constant(data, target, registry):
    return apply(data, target, registry)


RELATIONAL = {'>=': '>', '>': '>=', '<=': '<', '<': '<=', '==': '!=', '!=': '=='}
LOGIC = {'&': '|', '|': '&', '&&': '||', '||': '&&'}
NEW_OPERATORS = {'relational_operator_replace', 'condition_invert', 'logic_operator_swap'}


def _predicate(node):
    conditions = list(node.predicate.conditions)
    if len(conditions) != 1 or conditions[0].matchesClause is not None:
        raise ValueError('Condition must be a single expression, without pattern matching')
    return conditions[0].expr


def _generated(path):
    return PurePosixPath(path).name.endswith(('_reg_top.sv', '_reg_pkg.sv'))


def _context(source, node, op):
    source.single_line(node)
    child = node
    for parent in ancestors(node):
        name = kind(parent)
        if 'Generate' in name:
            if op != 'relational_operator_replace':
                raise ValueError('Generate sites excluded')
            if name not in {'GenerateBlock', 'GenerateRegion'} and (
                    kind(child).endswith(('Expression', 'Name')) or kind(child) == 'ConditionalPredicate'):
                raise ValueError('Generate condition excluded')
        if op == 'logic_operator_swap' and any(s in name for s in ('Assert', 'Property', 'Cover')):
            raise ValueError('Assertion/cover property excluded')
        child = parent


def _site_nodes(source, op):
    for node in source.nodes:
        if op == 'condition_invert':
            if kind(node) in {'ConditionalStatement', 'ConditionalExpression'}:
                yield node, _predicate(node)
        elif hasattr(node, 'operatorToken') and hasattr(node, 'left') and hasattr(node, 'right'):
            table = RELATIONAL if op == 'relational_operator_replace' else LOGIC
            if (node.operatorToken.rawText in (set(table) | ({'===', '!==', '==?', '!=?'} if op == 'relational_operator_replace' else set()))
                    and 'Assignment' not in kind(node)):
                yield node, node


def _operand(source, node, simple=False):
    if simple and kind(node) not in {'IdentifierName', 'IdentifierSelectName', 'ElementSelectExpression',
                                    'IntegerLiteralExpression', 'IntegerVectorExpression',
                                    'UnbasedUnsizedLiteralExpression'}:
        raise ValueError('Comparison operands must be identifiers, selects or literals')
    source.width(node)


def locate_operator(data, line, operator_id, expected_text, *, path, reset_identifiers=()):
    """Derive a proposed site; registry approval is enforced only by apply().

    Manifest reset names must be supplied by the caller in addition to defaults.
    The source path and reset policy are carried into the exact-checked target.
    """
    if operator_id not in NEW_OPERATORS:
        raise ValueError('Unknown operator')
    safe_path(path)
    if _generated(path):
        raise ValueError('Generated register file excluded')
    source = Source(data)
    _statement(source, line, expected_text, allow_comments=True)
    matches = [(owner, node) for owner, node in _site_nodes(source, operator_id)
               if source.line(node) == line]
    if len(matches) != 1:
        raise ValueError('Expected exactly one operator site on the declared line')
    owner, node = matches[0]
    _context(source, node, operator_id)
    extra = dict(lhs=None, rhs_tail=None, path=path, operator_id=operator_id,
                 reset_identifiers=sorted(set(reset_identifiers)))
    if operator_id == 'condition_invert':
        if {identifier(n) for n in walk(node) if kind(n) == 'IdentifierName'} & (
                {'rst_ni', 'rst_n', 'reset_n'} | set(reset_identifiers)):
            raise ValueError('Reset condition excluded')
        start, end = source.single_line(node)
        outer = node
        while kind(outer) == 'ParenthesizedExpression':
            outer = outer.expression
        if kind(outer) == 'UnaryLogicalNotExpression':
            # Remove only the outer ! token; all whitespace / parentheses survive.
            start, end = source.token_span(outer.operatorToken)
            after = ''
        else:
            after = '!(' + source.text(node) + ')'
        extra['construct'] = 'if_condition' if kind(owner) == 'ConditionalStatement' else 'ternary_condition'
    else:
        if operator_id == 'relational_operator_replace' and node.operatorToken.rawText not in RELATIONAL:
            raise ValueError('Case/wildcard equality excluded')
        _operand(source, node.left, simple=operator_id == 'relational_operator_replace')
        _operand(source, node.right, simple=operator_id == 'relational_operator_replace')
        start, end = source.token_span(node.operatorToken)
        after = (RELATIONAL if operator_id == 'relational_operator_replace' else LOGIC)[node.operatorToken.rawText]
        extra['construct'] = kind(node)
    return _record(source, line, expected_text, start, end, after, **extra)


def _apply_new(data, target, registry):
    if registry['version'] != '1.0' or registry['status'] != 'approved':
        raise ValueError('Operator is not an approved supported version')
    if sha(data) != target['file_sha256']:
        raise ValueError('Source hash does not match mutation proposal')
    actual = locate_operator(data, target['line'], registry['id'], target['statement'],
                             path=target['path'], reset_identifiers=target['reset_identifiers'])
    if actual != target:
        raise ValueError('Proposal coordinates or preconditions do not match source')
    changed = data[:target['start_byte']] + target['after'].encode('ascii') + data[target['end_byte']:]
    Source(changed)  # syntax must remain valid; the single splice is the entire edit
    return changed


def revert(data, target):
    """Reverse one exact edit, requiring the original hash after restoration."""
    start = target['start_byte']
    after = target['after'].encode('ascii')
    if data[start:start + len(after)] != after:
        raise ValueError('Edited bytes do not match')
    original = data[:start] + target['before'].encode('ascii') + data[start + len(after):]
    if sha(original) != target['file_sha256']:
        raise ValueError('Restoration does not match original hash')
    return original


def reachable_sites(data, *, path, reset_identifiers=()):
    """Enumerate approved-domain and proposed-domain sites without applying edits.

    Rejections are explicit (line, operator, reason). File parse errors propagate.
    """
    source = Source(data)
    lines = data.decode('ascii').splitlines()
    sites, rejected, attempts = {}, [], set()
    for node in source.nodes:
        if kind(node) == 'AssignmentExpression' and identifier(node.left):
            lhs = identifier(node.left)
            if kind(node.right) == 'AddExpression' and identifier(node.right.right):
                attempts.add(('unsigned32_root_add_to_sub', source.line(node), lhs, identifier(node.right.right)))
            if kind(node.right) in {'IntegerLiteralExpression', 'IntegerVectorExpression'}:
                attempts.add(('literal_lsb_flip32', source.line(node), lhs, None))
        if (kind(node) == 'Declarator' and kind(node.parent) == 'ParameterDeclaration'
                and node.parent.keyword.valueText == 'localparam' and node.initializer is not None):
            attempts.add(('literal_lsb_flip32', source.line(node), node.name.valueText, None))
    for op in sorted(NEW_OPERATORS):
        for owner, node in _site_nodes(source, op):
            attempts.add((op, source.line(node), '', ''))
    for op, line, lhs, tail in sorted(attempts):
        try:
            text = lines[line - 1].strip()
            if op == 'unsigned32_root_add_to_sub':
                target = locate(data, line, lhs, tail, text)
            elif op == 'literal_lsb_flip32':
                target = locate_constant(data, line, lhs, text)
            else:
                target = locate_operator(data, line, op, text, path=path, reset_identifiers=reset_identifiers)
            sites.setdefault(op, []).append(target)
        except ValueError as exc:
            rejected.append(dict(operator=op, line=line, reason=str(exc)))
    return {'sites': {op: sites.get(op, []) for op in [*LEGACY_MAPPERS, *sorted(NEW_OPERATORS)]},
            'rejected': rejected}
