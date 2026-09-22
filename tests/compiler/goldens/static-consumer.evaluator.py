x0 = X[0]
x1 = X[1]
x2 = X[2]
x3 = X[3]
x4 = X[4]
x5 = X[5]
k0 = frozenset(('https://json-schema.org/draft/2020-12/vocab/applicator#additionalProperties', 'https://json-schema.org/draft/2020-12/vocab/applicator#patternProperties', 'https://json-schema.org/draft/2020-12/vocab/applicator#properties', 'https://json-schema.org/draft/2020-12/vocab/unevaluated#unevaluatedProperties'))
k1 = ['string']

def u0(v, d, s, st, pn, cu, ev):
    if d >= H_MAXD:
        H_DEEP()
    d += 1
    m0 = len(ev)
    t0 = H_ENTER(st, x0, pn, cu)
    g0 = type(v) is dict
    w0 = True
    w1 = True
    m1 = H_EMARK(st)
    if g0:
        b0 = []
        if 'a' in v:
            b0.append('a')
            m2 = H_AMARK(st)
            if not u1(v['a'], d, s, st, H_PATH(pn, 'properties/a'), H_CHILD(cu, 'a', v['a'])):
                w0 = False
                H_ACUT(st, m2)
        if w0:
            ev.append(('https://json-schema.org/draft/2020-12/vocab/applicator#properties', b0))
    if w0:
        H_DROP(st, m1)
    m3 = H_EMARK(st)
    if g0:
        b1 = H_COVN(ev[m0:], k0)
        b2 = []
        for b3 in v:
            if b3 not in b1:
                b2.append(b3)
                m4 = H_AMARK(st)
                if not H_FALSE(st, x3, H_PATH(pn, 'unevaluatedProperties'), H_CHILD(cu, b3, v[b3])):
                    w1 = False
                    H_ACUT(st, m4)
        if w1:
            ev.append(('https://json-schema.org/draft/2020-12/vocab/unevaluated#unevaluatedProperties', b2))
    if w1:
        H_DROP(st, m3)
    w2 = w0 and w1
    H_KWS(t0, 'properties', w0, 'unevaluatedProperties', w1)
    H_EXIT(st, t0, w2)
    return w2

def u1(v, d, s, st, pn, cu):
    t1 = H_ENTER(st, x4, pn, cu)
    w3 = True
    m5 = H_EMARK(st)
    if type(v) is not str:
        H_ERR(st, x5, pn, cu, 'expected string', {'expected': k1, 'actual': H_TYPE(v)})
        w3 = False
    if w3:
        H_DROP(st, m5)
    w4 = w3
    H_KWS(t1, 'type', w3)
    H_EXIT(st, t1, w4)
    return w4

def evaluate(v, st):
    try:
        return u0(v, 0, (), st, None, H_ROOT(v), [])
    except RecursionError:
        raise MaxDepthExceededError("compiled evaluation exceeded the interpreter's stack; reduce nesting or lower max_depth") from None
