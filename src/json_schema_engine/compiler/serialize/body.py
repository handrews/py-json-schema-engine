# Serializing a unit body (M6): IR expressions to `ast` expressions, IR
# statements to `ast` statements, subschema applications to unit calls,
# trampolines, boolean folds, or inlined bodies. Expressions, statements,
# and applications are mutually recursive, so they live in one module.
#
# Dependency direction: imports `emit`, `context`, `units`, the planner,
# and core's IR and `json_model`. The module assembler imports this.

import ast

from json_schema_engine.compiler import emit as e
from json_schema_engine.compiler.plan import PlannedUnit, schema_value
from json_schema_engine.compiler.serialize.context import (
    BodyContext,
    EdgeKey,
    SerializeError,
)
from json_schema_engine.compiler.serialize.units import (
    UnitIR,
    ir_loop_height,
    lower_unit,
    uses_object_test,
)
from json_schema_engine.core.json_model import JsonValue
from json_schema_engine.core.lowering import (
    Apply,
    ApplyExpr,
    Binding,
    Child,
    Cmp,
    CombineCheck,
    Const,
    CountRange,
    Expr,
    Fail,
    ForEachIndex,
    ForEachKey,
    HasKey,
    Helper,
    HelperName,
    Here,
    If,
    InConsts,
    Instance,
    Item,
    Key,
    Logic,
    LowerApply,
    LowerCursor,
    Member,
    Not,
    RegexTest,
    Stmt,
    TypeIs,
    TypeName,
)

_CMP_OPS: dict[str, type[ast.cmpop]] = {
    "<": ast.Lt,
    "<=": ast.LtE,
    ">": ast.Gt,
    ">=": ast.GtE,
    "==": ast.Eq,
    "!=": ast.NotEq,
}


def _is_number(x: ast.expr) -> ast.expr:
    return e.or_(e.type_is(x, "int"), e.type_is(x, "float"))


def _type_test(
    body: BodyContext, x: ast.expr, name: TypeName, guarded: bool
) -> ast.expr:
    match name:
        case "object":
            if guarded and body.guard is not None:
                return e.load(body.guard)
            return e.type_is(x, "dict")
        case "array":
            return e.type_is(x, "list")
        case "string":
            return e.type_is(x, "str")
        case "boolean":
            return e.type_is(x, "bool")
        case "null":
            return e.is_(x, ast.Constant(value=None))
        case "number":
            return _is_number(x)
        case "integer":
            # P2: `1.0` is an integer, `True` is not a number at all.
            return e.or_(
                e.type_is(x, "int"),
                e.and_(e.type_is(x, "float"), e.call(e.attr(x, "is_integer"))),
            )


def _const_operand(body: BodyContext, value: JsonValue) -> ast.expr:
    """A constant as an operand: scalars inline, containers hoisted once."""
    if isinstance(value, list | dict):
        return e.load(body.fn.module.hoist(e.const(value)))
    return e.const(value)


def _equal_to_const(body: BodyContext, x: ast.expr, value: JsonValue) -> ast.expr:
    """`json_equal(x, value)` specialized on the constant's type (P2)."""
    if value is None:
        return e.is_(x, ast.Constant(value=None))
    if isinstance(value, bool):
        return e.is_(x, ast.Constant(value=value))
    if isinstance(value, str):
        return e.and_(e.type_is(x, "str"), e.compare(x, ast.Eq(), e.const(value)))
    if isinstance(value, int | float):
        return e.and_(_is_number(x), e.compare(x, ast.Eq(), e.const(value)))
    return e.call(e.load(e.H_EQ), x, _const_operand(body, value))


def _in_consts(
    body: BodyContext, target: Expr, values: tuple[JsonValue, ...]
) -> ast.expr:
    x = expression(body, target)
    if not values:
        return ast.Constant(value=False)
    specialize = body.fn.module.flags.specialize_sets
    all_str = all(isinstance(v, str) for v in values)
    all_num = all(
        isinstance(v, int | float) and not isinstance(v, bool) for v in values
    )
    if specialize and len(values) >= 2 and (all_str or all_num):
        table = e.load(
            body.fn.module.hoist(e.frozenset_literal(sorted(values, key=repr)))
        )
        if all_str:
            # A swept key is always a string; anything else needs the guard,
            # since `1 in frozenset({"1"})` is well-defined but wrong here.
            guard = () if _is_swept_key(body, target) else (e.type_is(x, "str"),)
            return e.and_(*guard, e.in_(x, table))
        return e.and_(_is_number(x), e.in_(x, table))
    return e.or_(*(_equal_to_const(body, x, v) for v in values))


def _is_swept_key(body: BodyContext, target: Expr) -> bool:
    return isinstance(target, Binding) and target.id in body.key_bindings


def expression(body: BodyContext, expr: Expr) -> ast.expr:
    match expr:
        case Instance():
            return e.load(body.value)
        case Const(value):
            return _const_operand(body, value)
        case Member(target, key):
            return e.subscript(expression(body, target), e.const(key))
        case Item(target, index):
            return e.subscript(expression(body, target), expression(body, index))
        case Binding(binding):
            return e.load(body.binding_name(binding))
        case TypeIs(target, types):
            x = expression(body, target)
            guarded = isinstance(target, Instance)
            return e.or_(*(_type_test(body, x, name, guarded) for name in types))
        case HasKey(target, key):
            key_expr = e.const(key) if isinstance(key, str) else expression(body, key)
            return e.in_(key_expr, expression(body, target))
        case Cmp(op, left, right):
            return e.compare(
                expression(body, left), _CMP_OPS[op](), expression(body, right)
            )
        case Helper(name, args):
            return _helper(body, name, args)
        case InConsts(target, values):
            return _in_consts(body, target, values)
        case RegexTest(source, target):
            pattern = e.load(body.fn.module.regex_name(source))
            return e.is_not(
                e.call(e.attr(pattern, "search"), expression(body, target)),
                ast.Constant(value=None),
            )
        case Not(inner):
            return e.not_(expression(body, inner))
        case Logic(op, parts):
            rendered = [expression(body, p) for p in parts]
            return e.and_(*rendered) if op == "and" else e.or_(*rendered)
        case ApplyExpr(apply):
            return apply_expression(body, apply)


def _helper(body: BodyContext, name: HelperName, args: tuple[Expr, ...]) -> ast.expr:
    match name:
        case "json_equal":
            left, right = args
            if isinstance(right, Const):
                return _equal_to_const(body, expression(body, left), right.value)
            if isinstance(left, Const):
                return _equal_to_const(body, expression(body, right), left.value)
            return e.call(
                e.load(e.H_EQ), expression(body, left), expression(body, right)
            )
        case "is_multiple_of":
            return e.call(e.load(e.H_MOF), *(expression(body, a) for a in args))
        case "has_duplicate_items":
            return e.call(e.load(e.H_DUP), *(expression(body, a) for a in args))
        case "length_of" | "code_point_length":
            # `len` counts code points on `str` and elements on containers.
            (arg,) = args
            return e.call(e.load("len"), expression(body, arg))


# --- applications ------------------------------------------------------------


def edge_key(keyword: str, apply: LowerApply) -> EdgeKey:
    return (keyword, apply.sibling, apply.ref, apply.path)


def cursor_value(body: BodyContext, cursor: LowerCursor) -> ast.expr:
    match cursor:
        case Here():
            return e.load(body.value)
        case Child(of, segment):
            index = (
                e.const(segment)
                if isinstance(segment, str | int)
                else expression(body, segment)
            )
            return e.subscript(cursor_value(body, of), index)
        case Key(binding):
            return e.load(body.binding_name(binding))


def _target_of(body: BodyContext, apply: LowerApply) -> PlannedUnit:
    key = body.edges.get(edge_key(body.keyword, apply))
    if key is None:
        raise SerializeError(
            f"{body.keyword!r} applies a subschema its facts never declared: "
            f"sibling={apply.sibling!r} ref={apply.ref!r} path={apply.path!r}"
        )
    return body.fn.module.plan.units[key]


def _call(body: BodyContext, target: PlannedUnit, value: ast.expr) -> ast.expr:
    """The verdict of applying `target` to `value` as an expression: a
    boolean literal, a unit call, or the trampoline."""
    module = body.fn.module
    node = target.ref.node
    if target.kind == "interpreted":
        body.fn.called_unit = True
        slot = module.target_slot(target.key)
        return e.call(
            e.load(e.H_FRAG),
            e.subscript(e.load(e.TARGETS), e.const(slot)),
            value,
            e.load(e.SCOPE),
            e.load(e.DEPTH),
        )
    if isinstance(node, bool):
        return ast.Constant(value=node)
    body.fn.called_unit = True
    return e.call(
        e.load(module.function_name(target.key)),
        value,
        e.load(e.DEPTH),
        e.load(e.SCOPE),
    )


def apply_expression(body: BodyContext, apply: LowerApply) -> ast.expr:
    return _call(body, _target_of(body, apply), cursor_value(body, apply.cursor))


def _can_inline(body: BodyContext, target: PlannedUnit) -> UnitIR | None:
    fn = body.fn
    flags = fn.module.flags
    if not flags.inline:
        return None
    if (
        target.kind != "static"
        or isinstance(target.ref.node, bool)
        or target.use_count != 1
        or target.reaches_interpreted
        or target.key in fn.inline_stack
        or len(fn.inline_stack) >= flags.inline_stack_cap
        or target.key in fn.module.functions
    ):
        return None
    ir = lower_unit(fn.module.registry, target)
    if fn.loop_depth + ir_loop_height(ir) > flags.loop_cap:
        return None
    return ir


def apply_statements(body: BodyContext, apply: LowerApply) -> list[ast.stmt]:
    """An `Apply` statement: fold the verdict into the keyword's verdict."""
    target = _target_of(body, apply)
    value = cursor_value(body, apply.cursor)
    if apply.fold == "all_must_pass":
        ir = _can_inline(body, target)
        if ir is not None:
            return inline_body(body, target, ir, apply.cursor, value)
        verdict = _call(body, target, value)
        if isinstance(verdict, ast.Constant):
            return [] if verdict.value else [e.return_(ast.Constant(value=False))]
        return [e.if_(e.not_(verdict), [e.return_(ast.Constant(value=False))])]
    verdict = _call(body, target, value)
    if apply.fold == "negate":
        if isinstance(verdict, ast.Constant):
            return [e.return_(ast.Constant(value=False))] if verdict.value else []
        return [e.if_(verdict, [e.return_(ast.Constant(value=False))])]
    if apply.fold == "discard":
        return [] if isinstance(verdict, ast.Constant) else [e.expr_stmt(verdict)]
    raise SerializeError(f"a {apply.fold} apply must be closed by a combine check")


def inline_body(
    body: BodyContext,
    target: PlannedUnit,
    ir: UnitIR,
    cursor: LowerCursor,
    value: ast.expr,
) -> list[ast.stmt]:
    """Emit `target`'s body in place: a `return False` inside it is the
    caller's failure too (licensed for `all_must_pass` only)."""
    fn = body.fn
    module = fn.module
    module.inlined.add(target.key)
    out: list[ast.stmt] = []
    if isinstance(cursor, Here):
        # Same instance: share the variable and its guard.
        inner = BodyContext(
            fn, target, schema_value(target.ref), body.value, {}, body.guard
        )
    else:
        temp = module.names.fresh("t")
        out.append(e.assign(temp, value))
        inner = BodyContext(fn, target, schema_value(target.ref), temp, {})
        if uses_object_test(ir):
            inner.guard = module.names.fresh("g")
            out.append(e.assign(inner.guard, e.type_is(e.load(temp), "dict")))
    inner.edges = edges_of(target)
    fn.inline_stack.append(target.key)
    try:
        out.extend(unit_statements(inner, ir))
    finally:
        fn.inline_stack.pop()
    return out


def edges_of(unit: PlannedUnit) -> dict[EdgeKey, str]:
    return {
        (edge.keyword, edge.app.sibling, edge.app.ref, edge.app.path): edge.target_key
        for edge in unit.edges
    }


# --- statements --------------------------------------------------------------


def unit_statements(body: BodyContext, ir: UnitIR) -> list[ast.stmt]:
    out: list[ast.stmt] = []
    for keyword, stmts in ir.keywords:
        body.keyword = keyword
        out.extend(statements(body, stmts))
    return out


def statements(body: BodyContext, stmts: tuple[Stmt, ...]) -> list[ast.stmt]:
    out: list[ast.stmt] = []
    run: list[LowerApply] = []
    run_fold: str | None = None
    false = ast.Constant(value=False)
    for stmt in stmts:
        if isinstance(stmt, Apply) and stmt.apply.fold in (
            "any_may_pass",
            "exactly_one",
        ):
            if run_fold is not None and run_fold != stmt.apply.fold:
                raise SerializeError("mixed combine folds in one run")
            run.append(stmt.apply)
            run_fold = stmt.apply.fold
            continue
        if isinstance(stmt, CombineCheck):
            out.extend(_flush_run(body, run, run_fold))
            run, run_fold = [], None
            continue
        if run:
            raise SerializeError("a combine run must be closed before other statements")
        match stmt:
            case If(cond, then, orelse):
                # A branch whose applications folded to `True` is empty;
                # Python has no empty block, and none is needed.
                then_stmts = statements(body, then)
                else_stmts = statements(body, orelse)
                if then_stmts:
                    out.append(e.if_(expression(body, cond), then_stmts, else_stmts))
                elif else_stmts:
                    out.append(e.if_(e.not_(expression(body, cond)), else_stmts))
            case ForEachKey(target, binding, loop_body):
                name = body.binding_name(binding)
                body.key_bindings.add(binding)
                loop_stmts = _loop(body, loop_body)
                if loop_stmts:
                    out.append(e.for_(name, expression(body, target), loop_stmts))
            case ForEachIndex(target, binding, loop_body, start):
                name = body.binding_name(binding)
                iterable = e.call(
                    e.load("range"),
                    e.const(start),
                    e.call(e.load("len"), expression(body, target)),
                )
                loop_stmts = _loop(body, loop_body)
                if loop_stmts:
                    out.append(e.for_(name, iterable, loop_stmts))
            case Fail():
                out.append(e.return_(false))
            case Apply(apply):
                out.extend(apply_statements(body, apply))
            case CountRange(target, binding, count_when, minimum, maximum, _, _):
                out.extend(
                    _count_range(body, target, binding, count_when, minimum, maximum)
                )
            case _:  # pragma: no cover - the match above is exhaustive
                raise SerializeError(f"unknown statement {stmt!r}")
    if run:
        raise SerializeError("a combine run must be closed by a combine check")
    return out


def _loop(body: BodyContext, stmts: tuple[Stmt, ...]) -> list[ast.stmt]:
    fn = body.fn
    fn.loop_depth += 1
    try:
        return statements(body, stmts)
    finally:
        fn.loop_depth -= 1


def _flush_run(
    body: BodyContext, run: list[LowerApply], fold: str | None
) -> list[ast.stmt]:
    false = ast.Constant(value=False)
    if fold is None or not run:
        # An empty `anyOf`/`oneOf` matches nothing.
        return [e.return_(false)]
    verdicts = [apply_expression(body, a) for a in run]
    if fold == "any_may_pass":
        # Licensed short-circuit (§4 rule 7): the planner islands every
        # consumer whose channel could observe these branches.
        return [e.if_(e.not_(e.or_(*verdicts)), [e.return_(false)])]
    counter = body.fn.module.names.fresh("c")
    out: list[ast.stmt] = [e.assign(counter, e.const(0))]
    for verdict in verdicts:
        if isinstance(verdict, ast.Constant):
            if verdict.value:
                out.append(e.aug_add(counter, e.const(1)))
            continue
        out.append(e.if_(verdict, [e.aug_add(counter, e.const(1))]))
    out.append(
        e.if_(e.compare(e.load(counter), ast.NotEq(), e.const(1)), [e.return_(false)])
    )
    return out


def _count_range(
    body: BodyContext,
    target: Expr,
    binding: int,
    count_when: Expr,
    minimum: int,
    maximum: int | None,
) -> list[ast.stmt]:
    false = ast.Constant(value=False)
    counter = body.fn.module.names.fresh("c")
    name = body.binding_name(binding)
    fn = body.fn
    fn.loop_depth += 1
    try:
        probe = expression(body, count_when)
    finally:
        fn.loop_depth -= 1
    iterable = e.call(e.load("range"), e.call(e.load("len"), expression(body, target)))
    out: list[ast.stmt] = [
        e.assign(counter, e.const(0)),
        e.for_(name, iterable, [e.if_(probe, [e.aug_add(counter, e.const(1))])]),
    ]
    if minimum > 0:
        out.append(
            e.if_(
                e.compare(e.load(counter), ast.Lt(), e.const(minimum)),
                [e.return_(false)],
            )
        )
    if maximum is not None:
        out.append(
            e.if_(
                e.compare(e.load(counter), ast.Gt(), e.const(maximum)),
                [e.return_(false)],
            )
        )
    return out
