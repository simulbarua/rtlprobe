"""One narrow, AST-checked arithmetic operator; never global text replacement."""

import hashlib
import re
import tempfile
from pathlib import PurePosixPath

from pyverilog.vparser.parser import VerilogParser


def sha(data):
    return hashlib.sha256(data).hexdigest()


def walk(node):
    yield node
    for child in node.children():
        yield from walk(child)


def safe_path(value):
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or str(path) != value or not path.parts:
        raise ValueError("Unsafe or noncanonical repository-relative path")
    return path


def parse(data):
    with tempfile.TemporaryDirectory(prefix="rtlprobe-parser-") as tmp:
        return VerilogParser(outputdir=tmp, debug=False).parse(data.decode("ascii"))


def locate(data, line, lhs, rhs_tail, expected_text):
    """Qualify a complete single-line unsigned 32-bit assignment from its AST."""
    nodes = list(walk(parse(data)))
    matches = [n for n in nodes if type(n).__name__ == "BlockingSubstitution"
               and n.lineno == line and getattr(n.left.var, "name", None) == lhs]
    if len(matches) != 1:
        raise ValueError("Expected exactly one AST assignment at declared site")
    expr = matches[0].right.var
    if type(expr).__name__ != "Plus" or getattr(expr.right, "name", None) != rhs_tail:
        raise ValueError("Site is not the supported root addition")
    if any(type(n).__name__ not in {"Plus", "Identifier"} for n in walk(expr)):
        raise ValueError("Only unsigned identifier-addition chains are supported")
    names = {n.name for n in walk(expr) if type(n).__name__ == "Identifier"} | {lhs}
    for name in names:
        declarations = [n for n in nodes if type(n).__name__ in {"Reg", "Wire"} and n.name == name]
        if len(declarations) != 1:
            raise ValueError(f"Ambiguous or missing declaration: {name}")
        decl = declarations[0]
        if (decl.signed or decl.width is None or getattr(decl.width.msb, "value", None) != "31"
                or getattr(decl.width.lsb, "value", None) != "0"):
            raise ValueError(f"Expected unsigned 32-bit declaration: {name}")
    lines = data.splitlines(keepends=True)
    raw = lines[line-1]
    if raw.strip().decode("ascii") != expected_text or b"//" in raw or b"/*" in raw:
        raise ValueError("Source statement does not match planned text")
    suffix = ("+ " + rhs_tail + ";").encode()
    if raw.count(suffix) != 1:
        raise ValueError("Ambiguous source token mapping")
    start = sum(map(len, lines[:line-1])) + raw.index(suffix)
    return {"line": line, "column_1based": raw.index(suffix)+1,
            "start_byte": start, "end_byte": start+1, "before": "+", "after": "-",
            "lhs": lhs, "rhs_tail": rhs_tail, "statement": expected_text,
            "file_sha256": sha(data), "mapper": "pyverilog-1.3.0+checked-single-line-span-v1"}


def apply(data, target, registry):
    if registry["id"] == "literal_lsb_flip32":
        return apply_constant(data, target, registry)
    if registry["id"] != "unsigned32_root_add_to_sub" or registry["version"] != "1.0" or registry["status"] != "approved":
        raise ValueError("Operator is not an approved supported version")
    if sha(data) != target["file_sha256"]:
        raise ValueError("Source hash does not match mutation proposal")
    actual = locate(data, target["line"], target["lhs"], target["rhs_tail"], target["statement"])
    if actual != target:
        raise ValueError("Proposal coordinates or preconditions do not match source")
    start, end = target["start_byte"], target["end_byte"]
    changed = data[:start] + b"-" + data[end:]
    matches = [n for n in walk(parse(changed)) if type(n).__name__ == "BlockingSubstitution"
               and n.lineno == target["line"] and getattr(n.left.var, "name", None) == target["lhs"]]
    if len(matches) != 1 or type(matches[0].right.var).__name__ != "Minus":
        raise ValueError("Post-mutation AST does not contain the intended subtraction")
    return changed


def literal_assignment(data, line, lhs):
    nodes = list(walk(parse(data)))
    if sum(type(n).__name__ == "ModuleDef" for n in nodes) != 1:
        raise ValueError("Constant mapper supports exactly one module")
    matches = []
    for node in nodes:
        if node.lineno != line:
            continue
        if type(node).__name__ == "Localparam" and node.name == lhs:
            matches.append((node.value.var, "localparam"))
        elif type(node).__name__ == "BlockingSubstitution" and getattr(node.left.var, "name", None) == lhs:
            matches.append((node.right.var, "assignment"))
    if len(matches) != 1 or type(matches[0][0]).__name__ != "IntConst":
        raise ValueError("Expected exactly one constant RHS at the declared AST site")
    literal, kind = matches[0]
    if kind == "assignment":
        decls = [n for n in nodes if type(n).__name__ == "Reg" and n.name == lhs]
        if (len(decls) != 1 or decls[0].signed or decls[0].width is None
                or getattr(decls[0].width.msb, "value", None) != "31"
                or getattr(decls[0].width.lsb, "value", None) != "0"):
            raise ValueError("Constant assignment requires an unsigned 32-bit register")
    return literal.value, kind


def flipped_literal(value):
    if re.fullmatch(r"32'h[0-9a-fA-F]{8}", value):
        return "32'h" + format(int(value[4:], 16) ^ 1, "08x")
    if re.fullmatch(r"0|[1-9][0-9]*", value) and int(value) < 2**31:
        return str(int(value) ^ 1)
    raise ValueError("Only 32-bit hex or nonnegative 32-bit-range unsized decimal literals supported")


def locate_constant(data, line, lhs, expected_text):
    before, kind = literal_assignment(data, line, lhs)
    after = flipped_literal(before)
    lines = data.splitlines(keepends=True)
    raw = lines[line-1]
    if raw.strip().decode("ascii") != expected_text or b"//" in raw or b"/*" in raw:
        raise ValueError("Source statement does not match planned text")
    suffix = ("= " + before + ";").encode()
    if raw.count(suffix) != 1:
        raise ValueError("Ambiguous literal source mapping")
    column = raw.index(suffix) + 2
    start = sum(map(len, lines[:line-1])) + column
    return {"line": line, "column_1based": column+1, "start_byte": start,
            "end_byte": start+len(before), "before": before, "after": after,
            "lhs": lhs, "rhs_tail": None, "statement": expected_text, "file_sha256": sha(data),
            "mapper": "pyverilog-1.3.0+checked-literal-span-v1", "construct": kind}


def apply_constant(data, target, registry):
    if registry["version"] != "1.0" or registry["status"] != "approved":
        raise ValueError("Unapproved constant operator")
    if sha(data) != target["file_sha256"]:
        raise ValueError("Source hash does not match mutation proposal")
    actual = locate_constant(data, target["line"], target["lhs"], target["statement"])
    if actual != target:
        raise ValueError("Constant coordinates or preconditions do not match source")
    changed = data[:target["start_byte"]] + target["after"].encode() + data[target["end_byte"]:]
    literal, kind = literal_assignment(changed, target["line"], target["lhs"])
    if literal != target["after"] or kind != target["construct"]:
        raise ValueError("Post-mutation constant AST mismatch")
    return changed
