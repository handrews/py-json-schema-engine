x0 = X[0]
x1 = X[1]
x2 = X[2]
x3 = X[3]
x4 = X[4]
x5 = X[5]
x6 = X[6]
x7 = X[7]
k0 = ['string']

def u0(v, d, s, st, pn, cu):
    if d >= H_MAXD:
        H_DEEP()
    d += 1
    t0 = H_ENTER(st, x0, pn, cu)
    g0 = type(v) is dict
    w0 = True
    m0 = H_EMARK(st)
    if g0:
        if 'p' in v:
            m1 = H_AMARK(st)
            if not u1(v['p'], d, s, st, H_PATH(pn, 'properties/p'), H_CHILD(cu, 'p', v['p'])):
                w0 = False
                H_ACUT(st, m1)
    if w0:
        H_DROP(st, m0)
    w1 = w0
    H_KWS(t0, 'properties', w0)
    H_EXIT(st, t0, w1)
    return w1

def u1(v, d, s, st, pn, cu):
    if d >= H_MAXD:
        H_DEEP()
    d += 1
    t1 = H_ENTER(st, x3, pn, cu)
    w2 = True
    m2 = H_EMARK(st)
    m3 = H_AMARK(st)
    if not u2(v, d, s, st, H_PATH(pn, '$dynamicRef'), cu):
        w2 = False
        H_ACUT(st, m3)
    if w2:
        H_DROP(st, m2)
    w3 = w2
    H_KWS(t1, '$dynamicRef', w2)
    H_EXIT(st, t1, w3)
    return w3

def u2(v, d, s, st, pn, cu):
    t2 = H_ENTER(st, x5, pn, cu)
    w4 = True
    m4 = H_EMARK(st)
    if type(v) is not str:
        H_ERR(st, x7, pn, cu, 'expected string', {'expected': k0, 'actual': H_TYPE(v)})
        w4 = False
    if w4:
        H_DROP(st, m4)
    w5 = w4
    H_KWS(t2, 'type', w4)
    H_EXIT(st, t2, w5)
    return w5

def evaluate(v, st):
    try:
        return u0(v, 0, (), st, None, H_ROOT(v))
    except RecursionError:
        raise MaxDepthExceededError("compiled evaluation exceeded the interpreter's stack; reduce nesting or lower max_depth") from None
