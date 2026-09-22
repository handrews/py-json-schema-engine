x0 = X[0]
x1 = X[1]
x2 = X[2]
x3 = X[3]
x4 = X[4]
x5 = X[5]
x6 = X[6]
x7 = X[7]
x8 = X[8]
x9 = X[9]
x10 = X[10]
x11 = X[11]
k0 = frozenset(('https://json-schema.org/draft/2020-12/vocab/applicator#additionalProperties', 'https://json-schema.org/draft/2020-12/vocab/applicator#patternProperties', 'https://json-schema.org/draft/2020-12/vocab/applicator#properties', 'https://json-schema.org/draft/2020-12/vocab/unevaluated#unevaluatedProperties'))
k1 = ['integer']
k2 = ['string']

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
    c0 = False
    m2 = H_AMARK(st)
    m3 = len(ev)
    if u1(v, d, s, st, H_PATH(pn, 'anyOf/0'), cu, ev):
        c0 = True
    else:
        H_ACUT(st, m2)
        del ev[m3:]
    m4 = H_AMARK(st)
    m5 = len(ev)
    if u2(v, d, s, st, H_PATH(pn, 'anyOf/1'), cu, ev):
        c0 = True
    else:
        H_ACUT(st, m4)
        del ev[m5:]
    if not c0:
        H_ERR(st, x1, pn, cu, 'does not match any anyOf branch', None)
        w0 = False
    if w0:
        H_DROP(st, m1)
    m6 = H_EMARK(st)
    if g0:
        b1 = H_COVN(ev[m0:], k0)
        b2 = []
        for b3 in v:
            if b3 not in b1:
                b2.append(b3)
                m7 = H_AMARK(st)
                if not H_FALSE(st, x3, H_PATH(pn, 'unevaluatedProperties'), H_CHILD(cu, b3, v[b3])):
                    w1 = False
                    H_ACUT(st, m7)
        if w1:
            ev.append(('https://json-schema.org/draft/2020-12/vocab/unevaluated#unevaluatedProperties', b2))
    if w1:
        H_DROP(st, m6)
    w2 = w0 and w1
    H_KWS(t0, 'anyOf', w0, 'unevaluatedProperties', w1)
    H_EXIT(st, t0, w2)
    return w2

def u1(v, d, s, st, pn, cu, ev):
    if d >= H_MAXD:
        H_DEEP()
    d += 1
    t1 = H_ENTER(st, x4, pn, cu)
    g1 = type(v) is dict
    w3 = True
    m8 = H_EMARK(st)
    if g1:
        b4 = []
        if 'a' in v:
            b4.append('a')
            m9 = H_AMARK(st)
            if not u3(v['a'], d, s, st, H_PATH(pn, 'properties/a'), H_CHILD(cu, 'a', v['a'])):
                w3 = False
                H_ACUT(st, m9)
        if w3:
            ev.append(('https://json-schema.org/draft/2020-12/vocab/applicator#properties', b4))
    if w3:
        H_DROP(st, m8)
    w4 = w3
    H_KWS(t1, 'properties', w3)
    H_EXIT(st, t1, w4)
    return w4

def u2(v, d, s, st, pn, cu, ev):
    if d >= H_MAXD:
        H_DEEP()
    d += 1
    t2 = H_ENTER(st, x6, pn, cu)
    g2 = type(v) is dict
    w5 = True
    m10 = H_EMARK(st)
    if g2:
        b5 = []
        if 'b' in v:
            b5.append('b')
            m11 = H_AMARK(st)
            if not u4(v['b'], d, s, st, H_PATH(pn, 'properties/b'), H_CHILD(cu, 'b', v['b'])):
                w5 = False
                H_ACUT(st, m11)
        if w5:
            ev.append(('https://json-schema.org/draft/2020-12/vocab/applicator#properties', b5))
    if w5:
        H_DROP(st, m10)
    w6 = w5
    H_KWS(t2, 'properties', w5)
    H_EXIT(st, t2, w6)
    return w6

def u3(v, d, s, st, pn, cu):
    t3 = H_ENTER(st, x8, pn, cu)
    w7 = True
    m12 = H_EMARK(st)
    if not (type(v) is int or (type(v) is float and v.is_integer())):
        H_ERR(st, x9, pn, cu, 'expected integer', {'expected': k1, 'actual': H_TYPE(v)})
        w7 = False
    if w7:
        H_DROP(st, m12)
    w8 = w7
    H_KWS(t3, 'type', w7)
    H_EXIT(st, t3, w8)
    return w8

def u4(v, d, s, st, pn, cu):
    t4 = H_ENTER(st, x10, pn, cu)
    w9 = True
    m13 = H_EMARK(st)
    if type(v) is not str:
        H_ERR(st, x11, pn, cu, 'expected string', {'expected': k2, 'actual': H_TYPE(v)})
        w9 = False
    if w9:
        H_DROP(st, m13)
    w10 = w9
    H_KWS(t4, 'type', w9)
    H_EXIT(st, t4, w10)
    return w10

def evaluate(v, st):
    try:
        return u0(v, 0, (), st, None, H_ROOT(v), [])
    except RecursionError:
        raise MaxDepthExceededError("compiled evaluation exceeded the interpreter's stack; reduce nesting or lower max_depth") from None
