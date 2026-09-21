k0 = frozenset(('https://json-schema.org/draft/2020-12/vocab/applicator#additionalProperties', 'https://json-schema.org/draft/2020-12/vocab/applicator#patternProperties', 'https://json-schema.org/draft/2020-12/vocab/applicator#properties', 'https://json-schema.org/draft/2020-12/vocab/unevaluated#unevaluatedProperties'))

def u0(v, d, s, ev):
    if d >= H_MAXD:
        H_DEEP()
    d += 1
    m0 = len(ev)
    g0 = type(v) is dict
    c0 = False
    m1 = len(ev)
    if u1(v, d, s, ev):
        c0 = True
    else:
        del ev[m1:]
    m1 = len(ev)
    if u2(v, d, s, ev):
        c0 = True
    else:
        del ev[m1:]
    if not c0:
        return False
    if g0:
        b0 = H_COVN(ev[m0:], k0)
        b1 = []
        for b2 in v:
            if b2 not in b0:
                b1.append(b2)
                return False
        ev.append(('https://json-schema.org/draft/2020-12/vocab/unevaluated#unevaluatedProperties', b1))
    return True

def u1(v, d, s, ev):
    if d >= H_MAXD:
        H_DEEP()
    d += 1
    if not u3(v, d, s, ev):
        return False
    return True

def u2(v, d, s, ev):
    g1 = type(v) is dict
    if g1:
        b3 = []
        if 'b' in v:
            b3.append('b')
            t0 = v['b']
            if type(t0) is not str:
                return False
        ev.append(('https://json-schema.org/draft/2020-12/vocab/applicator#properties', b3))
    return True

def u3(v, d, s, ev):
    g2 = type(v) is dict
    if g2:
        b4 = []
        if 'a' in v:
            b4.append('a')
            t1 = v['a']
            if not (type(t1) is int or (type(t1) is float and t1.is_integer())):
                return False
        ev.append(('https://json-schema.org/draft/2020-12/vocab/applicator#properties', b4))
    return True

def validate(v):
    try:
        return u0(v, 0, (), [])
    except RecursionError:
        raise MaxDepthExceededError("compiled evaluation exceeded the interpreter's stack; reduce nesting or lower max_depth") from None
