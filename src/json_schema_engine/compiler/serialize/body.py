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
from json_schema_engine.core.dialect import unknown_keyword_id
from json_schema_engine.core.json_model import JsonValue, escape_segment
from json_schema_engine.core.lowering import (
    Annotate,
    Append,
    Apply,
    ApplyExpr,
    Binding,
    Child,
    Cmp,
    Collect,
    CombineCheck,
    Cond,
    Const,
    CountRange,
    CoverageFold,
    Covers,
    Expr,
    Fail,
    ForEachIndex,
    ForEachKey,
    FormatTest,
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
    LowerMessage,
    LowerParams,
    Member,
    Not,
    Produce,
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


def _vocabulary_of(body: BodyContext) -> str | None:
    dialect = body.fn.module.registry.dialect_for(body.unit.ref.base_uri)
    entry = dialect.keywords.get(body.keyword)
    return entry.vocabulary_uri if entry is not None else None


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
        case FormatTest(name, target):
            predicate = e.load(body.fn.module.format_name(name))
            return e.call(predicate, expression(body, target))
        case Not(inner):
            return e.not_(expression(body, inner))
        case Logic(op, parts):
            rendered = [expression(body, p) for p in parts]
            return e.and_(*rendered) if op == "and" else e.or_(*rendered)
        case ApplyExpr(apply):
            if (body.channel is not None or body.evaluator) and isinstance(
                apply.cursor, Here
            ):
                # An in-place application inside an expression needs marks
                # around it; only `If` conditions are hoisted.
                raise SerializeError(
                    "in-place application inside an expression needs a statement"
                )
            return apply_expression(body, apply)
        case Cond(test, then, orelse):
            return e.if_expr(
                expression(body, test), expression(body, then), expression(body, orelse)
            )
        case Covers(fold, target):
            coverage = e.load(body.binding_name(fold))
            x = expression(body, target)
            if body.folds[fold] == "names":
                return e.in_(x, coverage)
            return e.or_(
                e.compare(x, ast.Lt(), e.subscript(coverage, e.const(0))),
                e.in_(x, e.subscript(coverage, e.const(1))),
            )


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
        case "first_duplicate_pair":
            return e.call(e.load(e.H_FDP), *(expression(body, a) for a in args))
        case "json_type_name":
            return e.call(e.load(e.H_TYPE), *(expression(body, a) for a in args))
        case "length_of" | "code_point_length":
            # `len` counts code points on `str` and elements on containers.
            (arg,) = args
            return e.call(e.load("len"), expression(body, arg))


# --- applications ------------------------------------------------------------


def edge_key(keyword: str, apply: LowerApply) -> EdgeKey:
    return (keyword, apply.sibling, apply.ref, apply.resolution, apply.path)


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


def _path_arg(body: BodyContext, apply: LowerApply) -> ast.expr:
    """The applied subschema's evaluation-path node: one synthetic node
    holding every segment the interpreter would mint (`materialize_path`
    joins them identically)."""
    head = apply.sibling if apply.sibling is not None else body.keyword
    joined = "/".join(escape_segment(str(s)) for s in (head, *apply.path))
    return e.call(e.load(e.H_PATH), e.load(body.path), e.const(joined))


def _cursor_arg(body: BodyContext, cursor: LowerCursor) -> ast.expr:
    """The applied subschema's cursor: a real `Cursor` chain, as the
    interpreter's `child_cursor` would build it."""
    match cursor:
        case Here():
            return e.load(body.cursor)
        case Child(of, segment):
            index = (
                e.const(segment)
                if isinstance(segment, str | int)
                else expression(body, segment)
            )
            return e.call(
                e.load(e.H_CHILD),
                _cursor_arg(body, of),
                index,
                cursor_value(body, cursor),
            )
        case Key(binding):
            name = e.load(body.binding_name(binding))
            return e.call(e.load(e.H_CHILD), e.load(body.cursor), name, name)


def _unit_site(body: BodyContext, unit: PlannedUnit) -> ast.expr:
    return e.load(
        body.fn.module.site_name(unit.key, None, (None, None, None, unit.ref))
    )


def _call(body: BodyContext, target: PlannedUnit, apply: LowerApply) -> ast.expr:
    """The verdict of applying `target` as an expression: a boolean literal
    (flag mode) or traced boolean application (evaluator mode), a unit
    call, or the trampoline.

    A target that takes a coverage channel (M9) receives this body's
    channel when applied in place inside a region, and a fresh list
    otherwise (coverage is per instance location, §4 rule 4).
    """
    module = body.fn.module
    node = target.ref.node
    value = cursor_value(body, apply.cursor)
    in_place = isinstance(apply.cursor, Here)
    shares_channel = in_place and body.channel is not None
    channel: ast.expr | None = None
    if target.takes_channel or target.kind == "interpreted":
        if shares_channel:
            assert body.channel is not None
            channel = e.load(body.channel)
        elif target.takes_channel:
            channel = e.list_literal()
    if body.evaluator:
        located = [_path_arg(body, apply), _cursor_arg(body, apply.cursor)]
        if target.kind == "interpreted":
            body.fn.called_unit = True
            slot = module.target_slot(target.key)
            return e.call(
                e.load(e.H_FRAGE),
                e.load(e.STATE),
                e.subscript(e.load(e.TARGETS), e.const(slot)),
                e.load(e.SCOPE),
                e.load(e.DEPTH),
                *located,
                channel if channel is not None else ast.Constant(value=None),
            )
        if isinstance(node, bool):
            helper = e.H_TRUE if node else e.H_FALSE
            return e.call(
                e.load(helper), e.load(e.STATE), _unit_site(body, target), *located
            )
        body.fn.called_unit = True
        args = [value, e.load(e.DEPTH), e.load(e.SCOPE), e.load(e.STATE), *located]
        if channel is not None:
            args.append(channel)
        return e.call(e.load(module.function_name(target.key)), *args)
    if target.kind == "interpreted":
        body.fn.called_unit = True
        slot = module.target_slot(target.key)
        args = [
            e.subscript(e.load(e.TARGETS), e.const(slot)),
            value,
            e.load(e.SCOPE),
            e.load(e.DEPTH),
        ]
        if channel is not None and shares_channel:
            return e.call(e.load(e.H_FRAGC), *args, channel)
        return e.call(e.load(e.H_FRAG), *args)
    if isinstance(node, bool):
        return ast.Constant(value=node)
    body.fn.called_unit = True
    args = [value, e.load(e.DEPTH), e.load(e.SCOPE)]
    if channel is not None:
        args.append(channel)
    return e.call(e.load(module.function_name(target.key)), *args)


def apply_expression(body: BodyContext, apply: LowerApply) -> ast.expr:
    return _call(body, _target_of(body, apply), apply)


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
        or target.takes_channel
        or target.key in fn.inline_stack
        or len(fn.inline_stack) >= flags.inline_stack_cap
        or target.key in fn.module.functions
    ):
        return None
    ir = lower_unit(fn.module.registry, target)
    if fn.loop_depth + ir_loop_height(ir) > flags.loop_cap:
        return None
    return ir


def _message(body: BodyContext, message: LowerMessage) -> ast.expr:
    """The interpreter's message text: constant parts joined with the
    `str()` of expression parts."""
    parts: list[ast.expr] = []
    for part in message:
        if isinstance(part, str):
            parts.append(e.const(part))
        else:
            parts.append(e.call(e.load("str"), expression(body, part)))
    if all(isinstance(p, ast.Constant) for p in parts):
        return e.const("".join(str(p.value) for p in parts))  # type: ignore[union-attr]
    out = parts[0]
    for part in parts[1:]:
        out = ast.BinOp(left=out, op=ast.Add(), right=part)
    return out


def _params(body: BodyContext, params: LowerParams | None) -> ast.expr:
    if params is None:
        return ast.Constant(value=None)
    return ast.Dict(
        keys=[e.const(k) for k in params],
        values=[expression(body, v) for v in params.values()],
    )


def _slot(body: BodyContext, sibling: str | None = None) -> str:
    """The verdict variable a failure clears: this keyword's, or the
    sibling keyword's for an `if`-driven `then`/`else`."""
    name = sibling if sibling is not None else body.keyword
    slot = body.slots.get(name)
    if slot is None:
        raise SerializeError(f"no verdict slot for keyword {name!r}")
    return slot


def _record_error(
    body: BodyContext,
    message: LowerMessage,
    params: LowerParams | None,
    sibling: str | None = None,
) -> list[ast.stmt]:
    """`H_ERR(st, xK, pn, cu, message, params)` then clear the slot."""
    return [
        e.expr_stmt(
            e.call(
                e.load(e.H_ERR),
                e.load(e.STATE),
                e.load(body.site),
                e.load(body.path),
                e.load(body.cursor),
                _message(body, message),
                _params(body, params),
            )
        ),
        e.assign(_slot(body, sibling), ast.Constant(value=False)),
    ]


def _ann_mark(body: BodyContext) -> tuple[str, ast.stmt]:
    """`mN = H_AMARK(st)`: where an application starts recording, so a
    failed application's annotations can be cut (§4 rule 3)."""
    name = body.fn.module.names.fresh("m")
    return name, e.assign(name, e.call(e.load(e.H_AMARK), e.load(e.STATE)))


def _ann_cut(mark: str) -> ast.stmt:
    return e.expr_stmt(e.call(e.load(e.H_ACUT), e.load(e.STATE), e.load(mark)))


def _err_mark(body: BodyContext) -> tuple[str, ast.stmt]:
    name = body.fn.module.names.fresh("m")
    return name, e.assign(name, e.call(e.load(e.H_EMARK), e.load(e.STATE)))


def _err_drop(mark: str) -> ast.stmt:
    return e.expr_stmt(e.call(e.load(e.H_DROP), e.load(e.STATE), e.load(mark)))


def _mark(body: BodyContext) -> tuple[str, ast.stmt]:
    """`mN = len(ev)`: where a region's in-place application starts writing,
    so a failed application's productions can be discarded (§4 rule 3)."""
    assert body.channel is not None
    name = body.fn.module.names.fresh("m")
    return name, e.assign(name, e.call(e.load("len"), e.load(body.channel)))


def _truncate(body: BodyContext, mark: str) -> ast.stmt:
    assert body.channel is not None
    return e.del_slice_from(body.channel, e.load(mark))


def _in_region(body: BodyContext, apply: LowerApply) -> bool:
    return body.channel is not None and isinstance(apply.cursor, Here)


def _evaluator_apply(body: BodyContext, apply: LowerApply) -> list[ast.stmt]:
    """An `Apply` statement in evaluator mode: every application runs, its
    annotations are marked and cut on failure, a failure clears the
    keyword's (or sibling's) verdict slot, and the unit continues."""
    verdict = apply_expression(body, apply)
    ann, marked = _ann_mark(body)
    cuts: list[ast.stmt] = [_ann_cut(ann)]
    out: list[ast.stmt] = [marked]
    if _in_region(body, apply):
        mark, ev_marked = _mark(body)
        cuts.append(_truncate(body, mark))
        out.append(ev_marked)
    if apply.fold == "all_must_pass":
        out.append(
            e.if_(
                e.not_(verdict),
                [
                    e.assign(_slot(body, apply.sibling), ast.Constant(value=False)),
                    *cuts,
                ],
            )
        )
        return out
    if apply.fold == "negate":
        assert apply.message is not None
        out.append(
            e.if_(verdict, _record_error(body, apply.message, apply.params), cuts)
        )
        return out
    if apply.fold == "discard":
        return _evaluator_discard(body, apply)[0]
    raise SerializeError(f"a {apply.fold} apply must be closed by a combine check")


def _evaluator_discard(
    body: BodyContext, apply: LowerApply
) -> tuple[list[ast.stmt], str]:
    """A `discard` application in evaluator mode (`if`'s condition, or a
    bare application): its errors are never relevant (rule 6), its records
    merge only when it passes. Returns the statements and the variable
    holding its verdict."""
    verdict = apply_expression(body, apply)
    ann, marked = _ann_mark(body)
    cuts: list[ast.stmt] = [_ann_cut(ann)]
    out: list[ast.stmt] = [marked]
    if _in_region(body, apply):
        mark, ev_marked = _mark(body)
        cuts.append(_truncate(body, mark))
        out.append(ev_marked)
    err, err_marked = _err_mark(body)
    temp = body.fn.module.names.fresh("t")
    out.append(err_marked)
    out.append(e.assign(temp, verdict))
    out.append(_err_drop(err))
    out.append(e.if_(e.not_(e.load(temp)), cuts))
    return out, temp


def apply_statements(body: BodyContext, apply: LowerApply) -> list[ast.stmt]:
    """An `Apply` statement: fold the verdict into the keyword's verdict."""
    if body.evaluator:
        return _evaluator_apply(body, apply)
    target = _target_of(body, apply)
    value = cursor_value(body, apply.cursor)
    false = ast.Constant(value=False)
    if apply.fold == "all_must_pass":
        ir = _can_inline(body, target)
        if ir is not None:
            return inline_body(body, target, ir, apply.cursor, value)
        verdict = _call(body, target, apply)
        if isinstance(verdict, ast.Constant):
            return [] if verdict.value else [e.return_(false)]
        # A failure fails this unit, and the caller discards the channel
        # span, so no mark is needed here.
        return [e.if_(e.not_(verdict), [e.return_(false)])]
    verdict = _call(body, target, apply)
    if apply.fold == "negate":
        if isinstance(verdict, ast.Constant):
            return [e.return_(false)] if verdict.value else []
        if _in_region(body, apply):
            # A failing negated subschema's productions must not survive.
            mark, marked = _mark(body)
            return [marked, e.if_(verdict, [e.return_(false)]), _truncate(body, mark)]
        return [e.if_(verdict, [e.return_(false)])]
    if apply.fold == "discard":
        if isinstance(verdict, ast.Constant):
            return []
        if _in_region(body, apply):
            mark, marked = _mark(body)
            return [marked, e.if_(e.not_(verdict), [_truncate(body, mark)])]
        return [e.expr_stmt(verdict)]
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
        (
            edge.keyword,
            edge.app.sibling,
            edge.app.ref,
            edge.app.resolution,
            edge.app.path,
        ): edge.target_key
        for edge in unit.edges
    }


# --- statements --------------------------------------------------------------


def unit_statements(body: BodyContext, ir: UnitIR) -> list[ast.stmt]:
    if body.evaluator:
        return _evaluator_unit_statements(body, ir)
    out: list[ast.stmt] = []
    for keyword in ir.keywords:
        body.keyword = keyword.name
        body.behavior_id = keyword.behavior_id
        out.extend(statements(body, keyword.stmts))
    return out


def _has_sibling_apply(stmts: tuple[Stmt, ...]) -> bool:
    for stmt in stmts:
        match stmt:
            case Apply(apply) if apply.sibling is not None:
                return True
            case If(_, then, orelse):
                if _has_sibling_apply(then) or _has_sibling_apply(orelse):
                    return True
            case ForEachKey(_, _, loop_body) | ForEachIndex(_, _, loop_body, _):
                if _has_sibling_apply(loop_body):
                    return True
            case _:
                pass
    return False


def _evaluator_unit_statements(body: BodyContext, ir: UnitIR) -> list[ast.stmt]:
    """Every present keyword runs, in dialect order, with its own verdict
    slot: rule 6 marks the errors at its start and drops them when it
    accepts (a keyword driving sibling applications leaves theirs alone;
    its own condition dropped immediately). Unknown keywords annotate."""
    module = body.fn.module
    out: list[ast.stmt] = []
    for keyword in ir.keywords:
        if not keyword.structural:
            slot = module.names.fresh("w")
            body.slots[keyword.name] = slot
            out.append(e.assign(slot, ast.Constant(value=True)))
    for keyword in ir.keywords:
        body.keyword = keyword.name
        body.behavior_id = keyword.behavior_id
        body.site = module.site_name(
            body.unit.key,
            keyword.name,
            (keyword.behavior_id, keyword.name, keyword.vocabulary_uri, body.unit.ref),
        )
        if not keyword.stmts:
            continue
        err, marked = _err_mark(body)
        out.append(marked)
        out.extend(statements(body, keyword.stmts))
        if not keyword.structural and not _has_sibling_apply(keyword.stmts):
            out.append(e.if_(e.load(body.slots[keyword.name]), [_err_drop(err)]))
    for name in ir.unknown:
        if module.record is None or not module.record(name, None):
            continue
        site = module.site_name(
            body.unit.key, name, (unknown_keyword_id(name), name, None, body.unit.ref)
        )
        out.append(
            e.expr_stmt(
                e.call(
                    e.load(e.H_ANN),
                    e.load(e.STATE),
                    e.load(site),
                    e.load(body.path),
                    e.load(body.cursor),
                    _const_operand(body, body.schema[name]),
                )
            )
        )
    return out


def _if_statement(
    body: BodyContext, cond: Expr, then: tuple[Stmt, ...], orelse: tuple[Stmt, ...]
) -> list[ast.stmt]:
    # A branch whose applications folded to `True` is empty; Python has no
    # empty block, and none is needed.
    then_stmts = statements(body, then)
    else_stmts = statements(body, orelse)
    out: list[ast.stmt] = []
    if isinstance(cond, ApplyExpr) and body.evaluator:
        # `if`'s condition: an application whose errors are irrelevant and
        # whose records merge only when it passes; hoisted so the branch
        # reads its verdict.
        hoisted, temp = _evaluator_discard(body, cond.apply)
        out.extend(hoisted)
        test: ast.expr = e.load(temp)
    elif (
        isinstance(cond, ApplyExpr)
        and _in_region(body, cond.apply)
        and (then_stmts or else_stmts)
    ):
        # `if`'s condition in a tracked region: hoist the application so a
        # failing condition's productions are discarded before the branch.
        mark, marked = _mark(body)
        temp = body.fn.module.names.fresh("t")
        out.append(marked)
        out.append(e.assign(temp, apply_expression(body, cond.apply)))
        out.append(e.if_(e.not_(e.load(temp)), [_truncate(body, mark)]))
        test = e.load(temp)
    else:
        test = expression(body, cond)
    if then_stmts:
        out.append(e.if_(test, then_stmts, else_stmts))
    elif else_stmts:
        out.append(e.if_(e.not_(test), else_stmts))
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
            out.extend(_flush_run(body, run, run_fold, stmt))
            run, run_fold = [], None
            continue
        if run:
            raise SerializeError("a combine run must be closed before other statements")
        match stmt:
            case If(cond, then, orelse):
                out.extend(_if_statement(body, cond, then, orelse))
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
            case Fail(message, params):
                if body.evaluator:
                    out.extend(_record_error(body, message, params))
                else:
                    out.append(e.return_(false))
            case Apply(apply):
                out.extend(apply_statements(body, apply))
            case CountRange():
                out.extend(_count_range(body, stmt))
            case Collect(binding):
                if body.produce_live:
                    out.append(e.assign(body.binding_name(binding), e.list_literal()))
            case Append(binding, value, unique):
                if body.produce_live:
                    out.extend(_append(body, binding, value, unique))
            case Produce(value):
                if body.produce_live:
                    assert body.channel is not None
                    push = e.expr_stmt(
                        e.method_call(
                            e.load(body.channel),
                            "append",
                            e.tuple_(
                                (e.const(body.behavior_id), expression(body, value))
                            ),
                        )
                    )
                    # Dependency data comes only from an accepting keyword
                    # (rule 6); the flag tier's control flow guarantees it.
                    out.append(
                        e.if_(e.load(_slot(body)), [push]) if body.evaluator else push
                    )
            case CoverageFold(binding, half, consumes, contains_id, prefix_id):
                out.append(
                    _coverage_fold(
                        body, binding, half, consumes, contains_id, prefix_id
                    )
                )
            case Annotate():
                # The flag tier records nothing; the evaluator records the
                # keyword's own value unless the selection rules it out.
                record = body.fn.module.record
                if (
                    body.evaluator
                    and record is not None
                    and record(body.keyword, _vocabulary_of(body))
                ):
                    out.append(
                        e.expr_stmt(
                            e.call(
                                e.load(e.H_ANN),
                                e.load(e.STATE),
                                e.load(body.site),
                                e.load(body.path),
                                e.load(body.cursor),
                                _const_operand(body, body.schema[body.keyword]),
                            )
                        )
                    )
            case _:  # pragma: no cover - the match above is exhaustive
                raise SerializeError(f"unknown statement {stmt!r}")
    if run:
        raise SerializeError("a combine run must be closed by a combine check")
    return out


def _append(
    body: BodyContext, binding: int, value: Expr, unique: bool
) -> list[ast.stmt]:
    target = e.load(body.binding_name(binding))
    rendered = expression(body, value)
    call = e.expr_stmt(e.method_call(target, "append", rendered))
    if unique:
        return [e.if_(e.not_in(rendered, target), [call])]
    return [call]


def _coverage_fold(
    body: BodyContext,
    binding: int,
    half: str,
    consumes: tuple[str, ...],
    contains_id: str | None,
    prefix_id: str | None,
) -> ast.stmt:
    """`bN = H_COVN(ev[mark:], kC)` / `H_COVI(ev[mark:], len(v), kC, ...)`:
    the region channel folded once, by core's own folds."""
    if body.channel is None:
        raise SerializeError("a coverage fold outside a tracked unit")
    body.folds[binding] = half
    entries: ast.expr = e.load(body.channel)
    if body.channel_mark is not None:
        entries = ast.Subscript(
            value=entries,
            slice=ast.Slice(lower=e.load(body.channel_mark), upper=None, step=None),
            ctx=ast.Load(),
        )
    table = e.load(body.fn.module.hoist(e.frozenset_literal(sorted(consumes))))
    if half == "names":
        fold = e.call(e.load(e.H_COVN), entries, table)
    else:
        fold = e.call(
            e.load(e.H_COVI),
            entries,
            e.call(e.load("len"), e.load(body.value)),
            table,
            e.const(contains_id),
            e.const(prefix_id),
        )
    return e.assign(body.binding_name(binding), fold)


def _loop(body: BodyContext, stmts: tuple[Stmt, ...]) -> list[ast.stmt]:
    fn = body.fn
    fn.loop_depth += 1
    try:
        return statements(body, stmts)
    finally:
        fn.loop_depth -= 1


def _evaluator_run(
    body: BodyContext, run: list[LowerApply], fold: str, check: CombineCheck
) -> list[ast.stmt]:
    """A combine run in evaluator mode: every branch runs with its own
    annotation (and channel) mark; the keyword's error names the outcome."""
    names = body.fn.module.names
    out: list[ast.stmt] = []
    counter = names.fresh("c")
    passing = names.fresh("b")
    if fold == "any_may_pass":
        out.append(e.assign(counter, ast.Constant(value=False)))
        hit: list[ast.stmt] = [e.assign(counter, ast.Constant(value=True))]
        failed_test: ast.expr = e.not_(e.load(counter))
    else:
        out.append(e.assign(counter, e.const(0)))
        out.append(e.assign(passing, e.list_literal()))
        if check.count is not None:
            body.bindings[check.count] = counter
        if check.passing is not None:
            body.bindings[check.passing] = passing
        hit = [
            e.aug_add(counter, e.const(1)),
            e.expr_stmt(e.method_call(e.load(passing), "append", e.const(0))),
        ]
        failed_test = e.compare(e.load(counter), ast.NotEq(), e.const(1))
    for position, apply in enumerate(run):
        verdict = apply_expression(body, apply)
        ann, marked = _ann_mark(body)
        cuts: list[ast.stmt] = [_ann_cut(ann)]
        out.append(marked)
        if _in_region(body, apply):
            mark, ev_marked = _mark(body)
            out.append(ev_marked)
            cuts.append(_truncate(body, mark))
        if fold != "any_may_pass":
            hit = [
                e.aug_add(counter, e.const(1)),
                e.expr_stmt(
                    e.method_call(e.load(passing), "append", e.const(position))
                ),
            ]
        out.append(e.if_(verdict, hit, cuts))
    out.append(e.if_(failed_test, _record_error(body, check.message, check.params)))
    return out


def _flush_run(
    body: BodyContext,
    run: list[LowerApply],
    fold: str | None,
    check: CombineCheck | None = None,
) -> list[ast.stmt]:
    false = ast.Constant(value=False)
    if body.evaluator:
        assert check is not None
        if fold is None or not run:
            # An empty `anyOf`/`oneOf` matches nothing.
            return _record_error(body, check.message, check.params)
        return _evaluator_run(body, run, fold, check)
    if fold is None or not run:
        # An empty `anyOf`/`oneOf` matches nothing.
        return [e.return_(false)]
    region = body.channel is not None and any(isinstance(a.cursor, Here) for a in run)
    verdicts = [apply_expression(body, a) for a in run]
    if fold == "any_may_pass" and not region:
        # Licensed short-circuit (§4 rule 7): the planner islands every
        # consumer whose channel could observe these branches.
        return [e.if_(e.not_(e.or_(*verdicts)), [e.return_(false)])]
    names = body.fn.module.names
    counter = names.fresh("c")
    out: list[ast.stmt] = []
    if fold == "any_may_pass":
        # Inside a tracked region every branch runs (§4 rule 7 lifted): a
        # passing branch's productions stay, a failing branch's are cut.
        out.append(e.assign(counter, ast.Constant(value=False)))
        mark = names.fresh("m")
        for verdict in verdicts:
            if isinstance(verdict, ast.Constant):
                if verdict.value:
                    out.append(e.assign(counter, ast.Constant(value=True)))
                continue
            out.append(e.assign(mark, e.call(e.load("len"), e.load(e.CHANNEL))))
            out.append(
                e.if_(
                    verdict,
                    [e.assign(counter, ast.Constant(value=True))],
                    [_truncate(body, mark)],
                )
            )
        out.append(e.if_(e.not_(e.load(counter)), [e.return_(false)]))
        return out
    # `exactly_one`: every branch runs until a second success, which
    # settles the verdict (a licensed early exit, §4 rule 7); inside a
    # tracked region every branch runs and failed ones are cut.
    out.append(e.assign(counter, e.const(0)))
    too_many = e.if_(
        e.compare(e.load(counter), ast.Gt(), e.const(1)), [e.return_(false)]
    )
    mark = names.fresh("m") if region else None
    for position, verdict in enumerate(verdicts):
        increment: list[ast.stmt] = [e.aug_add(counter, e.const(1))]
        if position > 0 and not region:
            increment.append(too_many)
        if isinstance(verdict, ast.Constant):
            if verdict.value:
                out.extend(increment)
            continue
        if mark is not None:
            out.append(e.assign(mark, e.call(e.load("len"), e.load(e.CHANNEL))))
            out.append(e.if_(verdict, increment, [_truncate(body, mark)]))
        else:
            out.append(e.if_(verdict, increment))
    out.append(
        e.if_(e.compare(e.load(counter), ast.NotEq(), e.const(1)), [e.return_(false)])
    )
    return out


def _count_range(body: BodyContext, stmt: CountRange) -> list[ast.stmt]:
    false = ast.Constant(value=False)
    counter = body.fn.module.names.fresh("c")
    if stmt.count is not None:
        body.bindings[stmt.count] = counter
    name = body.binding_name(stmt.binding)
    fn = body.fn
    fn.loop_depth += 1
    try:
        probe = expression(body, stmt.count_when)
    finally:
        fn.loop_depth -= 1
    iterable = e.call(
        e.load("range"), e.call(e.load("len"), expression(body, stmt.target))
    )
    # The matched indexes are dependency data: collected only when a
    # tracked consumer reads them.
    matched = (
        body.binding_name(stmt.matched)
        if stmt.matched is not None and body.produce_live
        else None
    )
    hit: list[ast.stmt] = [e.aug_add(counter, e.const(1))]
    if matched is not None:
        hit.append(e.expr_stmt(e.method_call(e.load(matched), "append", e.load(name))))
    if body.evaluator:
        # Every probe runs; its annotations merge only when it matches.
        ann, marked = _ann_mark(body)
        out: list[ast.stmt] = [e.assign(counter, e.const(0))]
        if matched is not None:
            out.append(e.assign(matched, e.list_literal()))
        out.append(e.for_(name, iterable, [marked, e.if_(probe, hit, [_ann_cut(ann)])]))
        bounds: list[ast.expr] = []
        if stmt.minimum > 0:
            bounds.append(e.compare(e.load(counter), ast.Lt(), e.const(stmt.minimum)))
        if stmt.maximum is not None:
            bounds.append(e.compare(e.load(counter), ast.Gt(), e.const(stmt.maximum)))
        if bounds:
            out.append(
                e.if_(e.or_(*bounds), _record_error(body, stmt.message, stmt.params))
            )
        return out
    if matched is None and stmt.maximum is None and stmt.minimum > 0:
        # Unbounded above and nobody reads the matches: reaching the
        # minimum settles the verdict, so the sweep stops there (§4 rule 7).
        hit.append(
            e.if_(
                e.compare(e.load(counter), ast.GtE(), e.const(stmt.minimum)),
                [ast.Break()],
            )
        )
    out = [e.assign(counter, e.const(0))]
    if matched is not None:
        out.append(e.assign(matched, e.list_literal()))
    out.append(e.for_(name, iterable, [e.if_(probe, hit)]))
    if stmt.minimum > 0:
        out.append(
            e.if_(
                e.compare(e.load(counter), ast.Lt(), e.const(stmt.minimum)),
                [e.return_(false)],
            )
        )
    if stmt.maximum is not None:
        out.append(
            e.if_(
                e.compare(e.load(counter), ast.Gt(), e.const(stmt.maximum)),
                [e.return_(false)],
            )
        )
    return out
