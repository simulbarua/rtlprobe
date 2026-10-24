"""Lossless pyslang syntax access. No preprocessing rewrites or source writes."""
from pyslang import SourceManager, ast
from pyslang.syntax import SyntaxNode, SyntaxTree


def walk(node):
    yield node
    for child in node:
        if isinstance(child, SyntaxNode):
            yield from walk(child)


def ancestors(node):
    while node.parent is not None:
        node = node.parent
        yield node


def kind(node):
    return node.kind.name


def identifier(node):
    return node.identifier.valueText if kind(node) == 'IdentifierName' else None


class Source:
    def __init__(self, data):
        self.data = data
        self.manager = SourceManager()
        self.tree = SyntaxTree.fromText(data.decode('ascii'), self.manager)
        errors = [str(d.code) for d in self.tree.diagnostics if d.isError()]
        if errors:
            raise ValueError('SystemVerilog syntax diagnostics: ' + ', '.join(errors))
        self.nodes = list(walk(self.tree.root))
        self.manager = self.tree.sourceManager
        self.buffer = self.manager.getAllBuffers()[0]
        self.compilation = None
        self.types = None

    def span(self, node):
        first, last = node.getFirstToken(), node.getLastToken()
        for token in (first, last):
            if (token.isMissing or self.manager.isMacroLoc(token.location)
                    or not self.manager.isFileLoc(token.location) or token.location.buffer != self.buffer):
                raise ValueError('Macro-derived or missing source token')
        start, end = first.location.offset, last.location.offset + len(last.rawText)
        if self.data[start:start + len(first.rawText)] != first.rawText.encode('ascii'):
            raise ValueError('Source token does not map to input bytes')
        return start, end

    def token_span(self, token):
        if (token.isMissing or self.manager.isMacroLoc(token.location)
                or not self.manager.isFileLoc(token.location) or token.location.buffer != self.buffer):
            raise ValueError('Macro-derived or missing source token')
        start = token.location.offset
        end = start + len(token.rawText)
        if self.data[start:end] != token.rawText.encode('ascii'):
            raise ValueError('Source token does not map to input bytes')
        return start, end

    def line(self, node):
        location = self.manager.getFullyExpandedLoc(node.getFirstToken().location)
        if location.buffer != self.buffer:
            raise ValueError('Site is outside the supplied source')
        return self.data[:location.offset].count(b'\n') + 1

    def single_line(self, node):
        start, end = self.span(node)
        if b'\n' in self.data[start:end] or b'\r' in self.data[start:end]:
            raise ValueError('Multiline site')
        # Check every token: first/last alone cannot detect a macro operand.
        def check(n):
            for child in n:
                if isinstance(child, SyntaxNode):
                    check(child)
                elif child:
                    self.token_span(child)
        check(node)
        return start, end

    def text(self, node):
        a, b = self.span(node)
        return self.data[a:b].decode('ascii')

    def width(self, node):
        if self.types is None:
            self.types = {}
            self.compilation = ast.Compilation()
            self.compilation.addSyntaxTree(self.tree)
            def visit(n):
                if isinstance(n, ast.Expression) and n.syntax is not None:
                    try:
                        key = self.span(n.syntax)
                    except ValueError:
                        return
                    t = n.type
                    value = (t.bitWidth, t.isSigned) if t.isIntegral and not n.bad else None
                    self.types.setdefault(key, set()).add(value)
            self.compilation.getRoot().visit(visit)
        values = self.types.get(self.span(node), set())
        if len(values) != 1 or None in values:
            raise ValueError('Operand width unresolved or ambiguous')
        width, signed = next(iter(values))
        if width <= 0:
            raise ValueError('Operand width unresolved')
        return width, signed
