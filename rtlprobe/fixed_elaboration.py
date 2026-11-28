"""Resolve parameters and conditional generate scopes for a fixed leaf DUT."""

from pyslang import ast
from pyslang.syntax import SyntaxTree

from .sv_frontend import kind


class FixedElaboration:
    def __init__(self, source, testbench, *, top, dut_scope):
        compilation = ast.Compilation()
        compilation.addSyntaxTree(source.tree)
        compilation.addSyntaxTree(SyntaxTree.fromText(testbench, source.manager, name='testbench.v'))
        root = compilation.getRoot()
        errors = [str(item.code) for item in compilation.getAllDiagnostics() if item.isError()]
        if errors:
            raise ValueError('Fixed DUT elaboration failed: '+', '.join(errors))
        test_top, instance = dut_scope.split('.')
        tests = [node for node in root.topInstances if node.name == test_top]
        instances = [node for node in tests[0].body if isinstance(node, ast.InstanceSymbol)
                     and node.name == instance and node.definition.name == top] if len(tests) == 1 else []
        if len(instances) != 1 or instances[0].hierarchicalPath != dut_scope:
            raise ValueError('Fixed elaboration requires the selected leaf DUT instance')
        self.scopes = {}
        self.inactive = []
        self.types = {}
        self._read(instances[0].body, source, ())

    def _read(self, body, source, prefix):
        for symbol in body:
            if isinstance(symbol, ast.GenerateBlockSymbol):
                span = source.span(symbol.syntax)
                if symbol.isUninstantiated:
                    self.inactive.append(span)
                else:
                    child = (*prefix, symbol.name)
                    self.scopes[span] = child
                    self._read(symbol, source, child)
            elif isinstance(symbol, (ast.InstanceSymbol, ast.GenerateBlockArraySymbol)):
                raise ValueError('Fixed elaboration supports a leaf DUT with conditional generates')
            elif isinstance(symbol, (ast.VariableSymbol, ast.NetSymbol, ast.ParameterSymbol)):
                dtype = symbol.type
                dimensions = []
                while isinstance(dtype, ast.FixedSizeUnpackedArrayType):
                    dimensions.append([dtype.range.left, dtype.range.right])
                    dtype = dtype.elementType
                key = '.'.join((*prefix, symbol.name))
                if key in self.types or not dtype.isIntegral or dtype.bitWidth < 1:
                    raise ValueError('Unsupported declaration in fixed DUT: '+key)
                self.types[key] = (dtype.bitWidth, dimensions)

    def prefix(self, source, node):
        start = source.span(node)[0]
        containing = [scope for (a, b), scope in self.scopes.items() if a <= start < b]
        return max(containing, key=len, default=())

    def active(self, source, node):
        start = source.span(node)[0]
        return not any(a <= start < b for a, b in self.inactive)

    def active_line(self, source, line):
        start = sum(map(len, source.data.splitlines(keepends=True)[:line-1]))
        end = source.data.find(b'\n', start)
        if end < 0:
            end = len(source.data)
        return not any(source.data[start:a].strip() == b'' and a < end <= b
                       or a <= start < b for a, b in self.inactive)

    @staticmethod
    def supports_invocation(node):
        if kind(node.left) != 'SystemName':
            return False
        name = str(node.left).strip()
        if name == '$clog2':
            return True
        if name in {'$error', '$finish'}:
            parent = node.parent
            while parent is not None:
                if kind(parent) == 'InitialBlock':
                    return True
                parent = parent.parent
        return False
