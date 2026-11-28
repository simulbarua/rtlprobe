"""Deterministic buggy-source syntax/dependency mapping; no execution or labels."""
from collections import defaultdict
from pyslang.syntax import SyntaxNode
import re
from .evidence import identity
from .mutation import safe_path, sha
from .sv_frontend import Source, ancestors, kind, walk

IDENT = re.compile(r'^[A-Za-z_][A-Za-z0-9_$]*$')
SCOPE = re.compile(r'^[A-Za-z_][A-Za-z0-9_$]*(?:\.[A-Za-z_][A-Za-z0-9_$]*)*$')
MAX_MEMORY_WORDS = 4096
ASSIGNMENTS = {'AssignmentExpression', 'NonblockingAssignmentExpression'}
UNSUPPORTED = {'LoopGenerate', 'IfGenerate', 'CaseGenerate', 'GenerateRegion',
               'TaskDeclaration', 'ClassDeclaration', 'InterfaceDeclaration',
               'WhileLoopStatement', 'DoWhileLoopStatement', 'ForeverLoopStatement', 'RepeatLoopStatement'}


def name_value(value):
    return value.valueText if hasattr(value, 'valueText') else value.identifier.valueText


def names(node):
    return {n.identifier.valueText for n in walk(node)
            if kind(n) in {'IdentifierName', 'IdentifierSelectName'}}


def owner(node):
    return next((p for p in ancestors(node) if kind(p) == 'ModuleDeclaration'), None)


def blocks(node):
    return tuple(reversed([p.blockName.name.valueText for p in ancestors(node)
                          if kind(p) == 'SequentialBlockStatement' and p.blockName is not None]))


def inside_function(node):
    return next((p for p in ancestors(node) if kind(p) == 'FunctionDeclaration'), None)


def literal_integer(text):
    text = text.strip().replace('_', '')
    if re.fullmatch(r'[0-9]+', text):
        return int(text)
    match = re.fullmatch(r"(?:[0-9]+)?'[sS]?([bBoOdDhH])([0-9a-fA-F]+)", text)
    if match:
        return int(match[2], {'b': 2, 'o': 8, 'd': 10, 'h': 16}[match[1].lower()])
    raise ValueError('nonliteral dimension')


def range_bounds(source, dimensions):
    bounds = []
    for dim in dimensions:
        selector = dim.specifier.selector
        if kind(selector) != 'SimpleRangeSelect':
            raise ValueError('only explicit constant ranges are supported')
        bounds.append([literal_integer(source.text(selector.left)), literal_integer(source.text(selector.right))])
    return bounds


def memory_capture_reason(ranges, remaining=MAX_MEMORY_WORDS):
    """Classify before expanding ranges; unsupported memory is never a zero count."""
    if len(ranges) > 1:
        return 'only one static unpacked dimension supported'
    if ranges and abs(ranges[0][0]-ranges[0][1])+1 > remaining:
        return 'explicit memory dump word budget exceeded'
    return None


def declarations(source, module, elaboration=None):
    result = {}
    for node in walk(module):
        if (kind(node) != 'Declarator' or inside_function(node)
                or elaboration is not None and not elaboration.active(source, node)):
            continue
        parent = node.parent
        if kind(parent) not in {'DataDeclaration', 'NetDeclaration', 'ImplicitAnsiPort', 'ParameterDeclaration'}:
            continue
        name = node.name.valueText
        prefix = elaboration.prefix(source, node) if elaboration else blocks(node)
        key = '.'.join((*prefix, name))
        if key in result:
            raise ValueError('ambiguous declaration ' + key)
        direction = None
        if kind(parent) == 'ImplicitAnsiPort':
            header = parent.header
            direction = str(header.direction).strip() if header is not None else None
            dtype = header.dataType if header is not None else None
        else:
            dtype = getattr(parent, 'type', None)
        width = None
        dimensions = []
        missing = []
        if not IDENT.fullmatch(name) or any(not IDENT.fullmatch(part) for part in prefix):
            missing.append('escaped or unsupported identifier')
        try:
            if elaboration is not None:
                width, dimensions = elaboration.types[key]
                reason = memory_capture_reason(dimensions)
                if reason:
                    missing.append(reason)
            else:
                dimensions = range_bounds(source, node.dimensions)
                reason = memory_capture_reason(dimensions)
                if reason:
                    missing.append(reason)
                packed = range_bounds(source, getattr(dtype, 'dimensions', []))
                if len(packed) > 1:
                    raise ValueError('multidimensional packed type')
                widths = {'IntegerType': 32, 'IntType': 32, 'ByteType': 8, 'ShortIntType': 16,
                          'LongIntType': 64, 'TimeType': 64, 'RegType': 1, 'LogicType': 1,
                          'BitType': 1, 'ImplicitType': 1}
                if packed:
                    width = abs(packed[0][0] - packed[0][1]) + 1
                elif kind(parent) == 'ParameterDeclaration' and node.initializer is not None:
                    literal = source.text(node.initializer.expr).strip()
                    sized = re.fullmatch(r"(\d+)'[sS]?[bBoOdDhH][0-9a-fA-F_xXzZ]+", literal)
                    width = int(sized[1]) if sized else (32 if re.fullmatch(r'[0-9_]+', literal) else None)
                    if width is None:
                        raise ValueError('constant expression width unresolved')
                elif dtype is not None and kind(dtype) in widths:
                    width = widths[kind(dtype)]
                else:
                    raise ValueError('unsupported or unresolved declaration type')
        except (ValueError, AttributeError) as error:
            missing.append(str(error))
        result[key] = {'name': name, 'local_name': key, 'path': None, 'line': source.line(node),
                       'kind': 'constant' if kind(parent) == 'ParameterDeclaration' else 'signal',
                       'direction': direction, 'width': width, 'unpacked_ranges': dimensions,
                       'missingness': missing}
    return result


def function_summary(source, function):
    """Recognize pure static expression functions, including crypto l2b byte swaps.

    Results are conservative argument dependencies, not a bit-accurate evaluator.
    State reads/writes, nested calls, timing, tasks and loops are rejected.
    """
    name = name_value(function.prototype.name)
    inputs = [n.declarator.name.valueText for n in walk(function) if kind(n) == 'FunctionPort']
    forbidden = [kind(n) for n in walk(function) if kind(n) in UNSUPPORTED
                 or kind(n) in {'InvocationExpression', 'TimingControlStatement', 'ForLoopStatement',
                                'NonblockingAssignmentExpression', 'FunctionDeclaration'} and n is not function]
    assignments = [n for n in walk(function) if kind(n) == 'AssignmentExpression']
    ports = [n for n in walk(function) if kind(n) == 'FunctionPort']
    valid = (IDENT.fullmatch(name) and all(IDENT.fullmatch(n) for n in inputs)
             and inputs and len(set(inputs)) == len(inputs) and assignments and not forbidden
             and all(str(n.direction).strip() in {'', 'input'} for n in ports)
             and all(kind(n.left) == 'IdentifierName' and n.left.identifier.valueText == name for n in assignments)
             and names(function) <= set(inputs) | {name})
    # Restrict to a single unconditional static return expression. This is enough
    # for the pinned ChaCha l2b function; more complex functions stay explicit.
    valid = bool(valid and len(assignments) == 1 and not any(kind(n) in {'ConditionalStatement', 'CaseStatement'} for n in walk(function)))
    return {'name': name, 'inputs': inputs, 'line': source.line(function),
            'status': 'supported_pure_static' if valid else 'unsupported',
            'semantics': 'conservative dependence on supplied arguments; no bit evaluation'}


def pure_function_lines(source, function, earlier):
    """Return the assignment lines of a checked straight-line call tree."""
    if str(function.prototype.lifetime).strip() != 'automatic':
        return None
    name = name_value(function.prototype.name)
    inputs = [n.declarator.name.valueText for n in walk(function) if kind(n) == 'FunctionPort']
    if not inputs or len(set(inputs)) != len(inputs) or name in inputs:
        return None
    ports = [n for n in walk(function) if kind(n) == 'FunctionPort']
    if any(str(port.direction).strip() not in {'', 'input'} or port.declarator.dimensions
           or port.declarator.initializer is not None for port in ports):
        return None
    items = list(function.items)
    if not items or kind(items[-1]) != 'SequentialBlockStatement' or items[-1].blockName is not None:
        return None
    locals_ = set()
    for declaration in items[:-1]:
        if kind(declaration) != 'DataDeclaration':
            return None
        for local in declaration.declarators:
            if not isinstance(local, SyntaxNode):
                continue
            local_name = local.name.valueText
            if local_name in locals_ or local_name in inputs or local_name == name:
                return None
            if local.initializer is not None or local.dimensions:
                return None
            locals_.add(local_name)
    initialized = set(inputs)
    lines = set()
    allowed = {'ArgumentList', 'BinaryAndExpression', 'BinaryXorExpression',
               'BitSelect', 'ConcatenationExpression', 'ElementSelect', 'IdentifierName',
               'IdentifierSelectName', 'IntegerLiteralExpression', 'IntegerVectorExpression',
               'InvocationExpression', 'MultipleConcatenationExpression', 'OrderedArgument',
               'ParenthesizedExpression', 'SimplePropertyExpr', 'SimpleRangeSelect', 'SimpleSequenceExpr'}
    statements = list(items[-1].items)
    for index, statement in enumerate(statements):
        if kind(statement) != 'ExpressionStatement' or kind(statement.expr) != 'AssignmentExpression':
            return None
        assignment = statement.expr
        if kind(assignment.left) != 'IdentifierName':
            return None
        lhs = assignment.left.identifier.valueText
        if lhs == name:
            if index != len(statements) - 1:
                return None
        elif lhs not in locals_:
            return None
        dependencies = set()
        for call in walk(assignment.right):
            call_kind = kind(call)
            if call_kind not in allowed:
                return None
            if call_kind in {'IdentifierName', 'IdentifierSelectName'} and not (
                    kind(call.parent) == 'InvocationExpression' and call.parent.left is call):
                dependencies.add(call.identifier.valueText)
            if call_kind != 'InvocationExpression':
                continue
            if kind(call.left) != 'IdentifierName' or call.arguments is None:
                return None
            called = call.left.identifier.valueText
            args = [a for a in call.arguments.parameters if isinstance(a, SyntaxNode)]
            if (called not in earlier or called in initialized or called in locals_
                    or len(args) != earlier[called][0] or any(kind(a) != 'OrderedArgument' for a in args)):
                return None
            lines.update(earlier[called][1])
        if dependencies - initialized:
            return None
        initialized.add(lhs)
        lines.add(source.line(assignment))
    return lines if name in initialized else None


def build_structure(sources, *, top, dut_scope, testbench=None):
    if not IDENT.fullmatch(top) or not SCOPE.fullmatch(dut_scope):
        raise ValueError('simple top and static DUT scope required')
    parsed, modules, syntax, unsupported = {}, {}, [], []
    for path, text in sorted(sources.items()):
        safe_path(path)
        try:
            source = Source(text.encode('ascii'))
        except (ValueError, UnicodeError) as error:
            unsupported.append({'path': path, 'line': None, 'kind': 'parse', 'reason': str(error)})
            continue
        parsed[path] = source
        positions = {id(node): index for index, node in enumerate(source.nodes)}
        for index, node in enumerate(source.nodes):
            try:
                start, end = source.span(node)
                syntax.append({'path': path, 'index': index, 'kind': kind(node), 'line': source.line(node),
                               'start_byte': start, 'end_byte': end,
                               'parent_index': positions.get(id(node.parent))})
            except ValueError as error:
                unsupported.append({'path': path, 'line': None, 'kind': kind(node), 'reason': str(error)})
            if kind(node) == 'ModuleDeclaration':
                name = node.header.name.valueText
                if name in modules:
                    raise ValueError('duplicate module declaration ' + name)
                modules[name] = (path, source, node)
    if top not in modules:
        raise ValueError('top module missing from buggy sources')
    nodes, edges, instances, functions, candidate_signals = {}, set(), [], [], defaultdict(set)
    unreachable = {}

    def visit(module_name, scope, ancestry=()):
        if module_name in ancestry or module_name not in modules:
            unsupported.append({'path': None, 'line': None, 'kind': 'hierarchy', 'reason': 'recursive or absent module ' + module_name})
            return
        path, source, module = modules[module_name]
        elaboration = None
        if testbench is not None:
            from .fixed_elaboration import FixedElaboration
            if len(sources) != 1:
                raise ValueError('Fixed elaboration requires one declared RTL source')
            elaboration = FixedElaboration(source, testbench, top=module_name, dut_scope=scope)
        decls = declarations(source, module, elaboration)
        function_nodes = [n for n in walk(module) if kind(n) == 'FunctionDeclaration']
        summaries = {}
        function_lines = {}
        for function in function_nodes:
            summary = function_summary(source, function)
            name = summary['name']
            if top == 'aes_core':
                lines = pure_function_lines(source, function, function_lines)
                if lines is not None:
                    function_lines[name] = (len(summary['inputs']), lines)
                    summary['status'] = 'supported_pure_static'
                else:
                    summary['status'] = 'unsupported'
            elif summary['status'] == 'supported_pure_static':
                function_lines[name] = (len(summary['inputs']),
                    {source.line(node) for node in walk(function) if kind(node) in ASSIGNMENTS})
            summaries[name] = summary
        if top == 'aes_core' and function_lines:
            used = set()
            for node in walk(module):
                if (kind(node) == 'InvocationExpression' and not inside_function(node)
                        and kind(node.left) == 'IdentifierName'):
                    summary = function_lines.get(node.left.identifier.valueText)
                    if summary:
                        used.update(summary[1])
            # A pure function with no path from a module call cannot produce a signal.
            defined = set().union(*(summary[1] for summary in function_lines.values()))
            unreachable.update({(path, module_name, line, scope): 'pure function has no call path from the DUT instance'
                                for line in defined - used})
        instances.append({'instance': scope, 'module': module_name, 'path': path})
        for summary in summaries.values():
            functions.append({**summary, 'instance': scope, 'path': path})
            if summary['status'] == 'unsupported':
                unsupported.append({'path': path, 'line': summary['line'], 'kind': 'function', 'reason': summary['name']})
        for local, declaration in decls.items():
            signal = scope + '.' + local
            nodes[signal] = {**declaration, 'signal': signal, 'path': path, 'module': module_name, 'instance': scope}
        def resolve(name, at):
            prefix = elaboration.prefix(source, at) if elaboration else blocks(at)
            for length in range(len(prefix), -1, -1):
                local = '.'.join((*prefix[:length], name))
                if local in decls:
                    return scope + '.' + local
            return None
        def resolved(expr, at):
            values = set()
            for name in names(expr):
                signal = resolve(name, at)
                if signal:
                    values.add(signal)
                elif name not in summaries:
                    unsupported.append({'path': path, 'line': source.line(at), 'kind': 'unresolved_name', 'reason': name})
            return values
        for node in walk(module):
            k = kind(node)
            if elaboration and not elaboration.active(source, node):
                continue
            if k in UNSUPPORTED and not (elaboration and k in {'IfGenerate', 'GenerateRegion'}):
                unsupported.append({'path': path, 'line': source.line(node), 'kind': k, 'reason': 'unsupported elaboration/control construct'})
            if (not inside_function(node) and k == 'InvocationExpression'
                    and not (elaboration and elaboration.supports_invocation(node))):
                summary = summaries.get(node.left.identifier.valueText) if kind(node.left) == 'IdentifierName' else None
                if not summary or summary['status'] != 'supported_pure_static':
                    unsupported.append({'path': path, 'line': source.line(node), 'kind': 'invocation',
                                        'reason': 'only checked pure static function calls supported'})
            if k.endswith('AssignmentExpression') and k not in ASSIGNMENTS:
                unsupported.append({'path': path, 'line': source.line(node), 'kind': k,
                                    'reason': 'compound assignment effects not mapped'})
            if (elaboration and k == 'Declarator' and kind(node.parent) in {'NetDeclaration', 'DataDeclaration'}
                    and node.initializer is not None):
                output = resolve(node.name.valueText, node)
                if output:
                    for incoming in resolved(node.initializer.expr, node):
                        edges.add((incoming, output, 'data', path, source.line(node)))
            if k in ASSIGNMENTS and not inside_function(node):
                # Select indices are dependencies, not additional assignment targets.
                if kind(node.left) in {'IdentifierName', 'IdentifierSelectName'}:
                    lhs_nodes = [node.left]
                elif kind(node.left) == 'ConcatenationExpression':
                    lhs_nodes = [n for n in walk(node.left) if kind(n) in {'IdentifierName', 'IdentifierSelectName'}
                                 and not any(kind(parent) == 'IdentifierSelectName' for parent in ancestors(n)
                                             if parent is not node.left)]
                else:
                    lhs_nodes = []
                    unsupported.append({'path': path, 'line': source.line(node), 'kind': 'assignment_target',
                                        'reason': 'unsupported lvalue expression'})
                outputs = {resolve(n.identifier.valueText, node) for n in lhs_nodes}
                outputs.discard(None)
                data = resolved(node.right, node)
                data |= resolved(node.left, node) - outputs
                controls = set()
                for parent in ancestors(node):
                    if kind(parent) == 'ConditionalStatement':
                        controls |= resolved(parent.predicate, node)
                    elif kind(parent) == 'CaseStatement':
                        controls |= resolved(parent.expr, node)
                    elif kind(parent) == 'ForLoopStatement':
                        controls |= resolved(parent.stopExpr, node)
                    elif kind(parent) in {'AlwaysBlock', 'AlwaysFFBlock', 'AlwaysCombBlock', 'AlwaysLatchBlock'}:
                        for event in walk(parent.statement):
                            if kind(event) == 'SignalEventExpression':
                                controls |= resolved(event.expr, node)
                for output in outputs:
                    for incoming in data:
                        edges.add((incoming, output, 'data', path, source.line(node)))
                    for incoming in controls:
                        edges.add((incoming, output, 'control', path, source.line(node)))
                candidate_signals[(path, module_name, source.line(node), scope)].update(outputs | data | controls)
                # A pure function's source candidate maps to every caller's actual
                # inputs/outputs, avoiding invented waveform variables for inlining.
                for call in walk(node.right):
                    if kind(call) == 'InvocationExpression' and kind(call.left) == 'IdentifierName':
                        summary = summaries.get(call.left.identifier.valueText)
                        if summary and summary['status'] == 'supported_pure_static':
                            for line in function_lines[summary['name']][1]:
                                candidate_signals[(path, module_name, line, scope)].update(outputs | data | controls)
                        else:
                            unsupported.append({'path': path, 'line': source.line(node), 'kind': 'function_call', 'reason': 'unresolved or unsupported function'})
            if k == 'HierarchyInstantiation':
                if any(kind(p) in UNSUPPORTED for p in ancestors(node)) or node.parameters is not None:
                    unsupported.append({'path': path, 'line': source.line(node), 'kind': 'instance', 'reason': 'generate or parameter override'})
                    continue
                child_name = node.type.valueText
                for child in node.instances:
                    if not hasattr(child, 'decl'):
                        continue
                    if child.decl.dimensions:
                        unsupported.append({'path': path, 'line': source.line(node), 'kind': 'instance_array', 'reason': 'not elaborated'})
                        continue
                    child_scope = scope + '.' + child.decl.name.valueText
                    visit(child_name, child_scope, (*ancestry, module_name))
                    for connection in child.connections:
                        if not isinstance(connection, SyntaxNode):
                            continue
                        if kind(connection) == 'NamedPortConnection' and connection.expr is None:
                            continue  # Explicitly unconnected port: no dependency edge.
                        if kind(connection) != 'NamedPortConnection':
                            unsupported.append({'path': path, 'line': source.line(node), 'kind': 'port', 'reason': 'only explicit connected named ports supported'})
                            continue
                        formal = child_scope + '.' + connection.name.valueText
                        declaration = nodes.get(formal)
                        if not declaration or declaration['direction'] not in {'input', 'output'}:
                            unsupported.append({'path': path, 'line': source.line(node), 'kind': 'port', 'reason': 'unknown direction or inout'})
                            continue
                        for actual in resolved(connection.expr, node):
                            edge = (actual, formal) if declaration['direction'] == 'input' else (formal, actual)
                            edges.add((*edge, 'port', path, source.line(node)))
        # Every candidate is mapped, including standalone conditions/constants.
        from .candidates import extract_candidates
        inventory = extract_candidates({path: sources[path]})
        for candidate in inventory['candidates']:
            if candidate['module'] != module_name:
                continue
            key = path, module_name, candidate['line'], scope
            if elaboration and not elaboration.active_line(source, candidate['line']):
                unreachable[key] = 'inactive conditional generate in the fixed DUT build'
                continue
            for node in source.nodes:
                if (owner(node) is module and source.line(node) == candidate['line'] and not inside_function(node)
                        and (not elaboration or elaboration.active(source, node))):
                    for name in set(candidate['lhs']) | set(candidate['dependencies']):
                        signal = resolve(name, node)
                        if signal:
                            candidate_signals[key].add(signal)
    visit(top, dut_scope)
    unique_unsupported = {identity(item): item for item in unsupported}
    graph = {'schema_version': 'buggy-dependencies-1', 'context': {'top': top, 'dut_scope': dut_scope},
             'nodes': [nodes[k] for k in sorted(nodes)],
             'edges': [{'source': a, 'target': b, 'kind': k, 'path': p, 'line': line} for a, b, k, p, line in sorted(edges)],
             'functions': sorted(functions, key=lambda f: (f['instance'], f['path'], f['line'])),
             'instances': sorted(instances, key=lambda i: i['instance']), 'ast': syntax,
             'unsupported': [unique_unsupported[k] for k in sorted(unique_unsupported)],
             'limitations': ['signal-level overapproximation, not bit/cycle causality',
                             'procedural loops and memories collapse at signal level; all static words are separately dumped',
                             'pure static functions conservatively connect all input arguments to each call output'],
             'status': 'partial' if unsupported or any(n['missingness'] for n in nodes.values()) else 'complete'}
    from .candidates import extract_candidates
    inventory = extract_candidates(sources)
    mappings = []
    for candidate in inventory['candidates']:
        found = False
        for instance in instances:
            if (instance['path'], instance['module']) != (candidate['path'], candidate['module']):
                continue
            location = (candidate['path'], candidate['module'], candidate['line'], instance['instance'])
            signals = sorted(candidate_signals[location])
            inactive = location in unreachable and graph['status'] == 'complete'
            mappings.append({'candidate_id': candidate.get('candidate_id', identity(candidate)), 'path': candidate['path'],
                             'module': candidate['module'], 'line': candidate['line'], 'instance': instance['instance'],
                             'signals': signals, 'status': 'mapped' if signals else 'unreachable' if inactive else 'unavailable',
                             'reason': None if signals else unreachable[location] if inactive
                             else 'no supported physical signal relation'})
            found = True
        if not found:
            mappings.append({'candidate_id': candidate.get('candidate_id', identity(candidate)), 'path': candidate['path'],
                             'module': candidate['module'], 'line': candidate['line'], 'instance': None, 'signals': [],
                             'status': 'unavailable', 'reason': 'module not in supported static DUT hierarchy'})
    missing = [m for m in mappings if m['status'] == 'unavailable']
    alignment = {'schema_version': 'buggy-alignment-1', 'inventory_id': inventory.get('inventory_id'),
                 'source_hashes': {p: sha(t.encode()) for p, t in sorted(sources.items())},
                 'mappings': mappings, 'missingness': missing,
                 'status': 'partial' if missing or graph['status'] == 'partial' else 'complete'}
    return graph, alignment


def observer_source(graph, *, max_memory_words=MAX_MEMORY_WORDS):
    """Only $dumpfile/$dumpvars calls: no checker, stimulus, finish or DUT writes."""
    scope = graph['context']['dut_scope']
    if not SCOPE.fullmatch(scope):
        raise ValueError('unsafe DUT scope')
    lines = ['module rtlprobe_observer;', 'integer comparison_ordinal = 0;', 'initial begin', '  $dumpfile("buggy.vcd");']
    missing, count, scalars = [], 0, 0
    for node in graph['nodes']:
        if not SCOPE.fullmatch(node['signal']):
            raise ValueError('observer requires safe static hierarchical identifiers')
        ranges = node['unpacked_ranges']
        if node['kind'] == 'constant':
            continue
        if not ranges:
            # A recursive module dump can omit an unused declaration during
            # elaboration. Explicit references retain its actual four-state value.
            lines.append(f"  $dumpvars(0, {node['signal']});")
            scalars += 1
            continue
        reason = memory_capture_reason(ranges, max_memory_words-count)
        if reason:
            missing.append({'signal': node['signal'], 'reason': reason})
            continue
        a, b = ranges[0]
        words = abs(a-b)+1
        for index in range(min(a,b), max(a,b)+1):
            lines.append(f"  $dumpvars(0, {node['signal']}[{index}]);")
        count += words
    lines.extend(['end', 'endmodule', ''])
    return '\n'.join(lines), {'policy': 'all statically mapped DUT signals and supported memory words, full run; no label/site selection',
                             'explicit_signals': scalars, 'explicit_memory_words': count, 'missingness': missing}
