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
x12 = X[12]
x13 = X[13]
x14 = X[14]
x15 = X[15]
x16 = X[16]
x17 = X[17]
x18 = X[18]
x19 = X[19]
x20 = X[20]
x21 = X[21]
x22 = X[22]
x23 = X[23]
x24 = X[24]
x25 = X[25]
x26 = X[26]
x27 = X[27]
x28 = X[28]

def u0(v, d, s, st, pn, cu):
    if d >= H_MAXD:
        H_DEEP()
    d += 1
    s = (*s, 'https://spike.example/island')
    t0 = H_ENTER(st, x0, pn, cu)
    w0 = True
    w1 = True
    w2 = True
    m0 = H_EMARK(st)
    m3 = H_AMARK(st)
    m4 = H_EMARK(st)
    t1 = u3(v, d, s, st, H_PATH(pn, 'if'), cu)
    H_DROP(st, m4)
    if not t1:
        H_ACUT(st, m3)
    if t1:
        m1 = H_AMARK(st)
        if not u1(v, d, s, st, H_PATH(pn, 'then'), cu):
            w1 = False
            H_ACUT(st, m1)
    else:
        m2 = H_AMARK(st)
        if not u2(v, d, s, st, H_PATH(pn, 'else'), cu):
            w2 = False
            H_ACUT(st, m2)
    w3 = w0 and w1 and w2
    H_KWS(t0, 'if', w0, 'then', w1, 'else', w2)
    H_EXIT(st, t0, w3)
    return w3

def u1(v, d, s, st, pn, cu):
    if d >= H_MAXD:
        H_DEEP()
    d += 1
    s = (*s, 'https://spike.example/island')
    t2 = H_ENTER(st, x5, pn, cu)
    g0 = type(v) is dict
    w4 = True
    m5 = H_EMARK(st)
    if g0:
        if 'list' in v:
            m6 = H_AMARK(st)
            if not u4(v['list'], d, s, st, H_PATH(pn, 'properties/list'), H_CHILD(cu, 'list', v['list'])):
                w4 = False
                H_ACUT(st, m6)
    if w4:
        H_DROP(st, m5)
    w5 = w4
    H_KWS(t2, 'properties', w4)
    H_EXIT(st, t2, w5)
    return w5

def u2(v, d, s, st, pn, cu):
    if d >= H_MAXD:
        H_DEEP()
    d += 1
    s = (*s, 'https://spike.example/island')
    t3 = H_ENTER(st, x7, pn, cu)
    g1 = type(v) is dict
    w6 = True
    m7 = H_EMARK(st)
    if g1:
        if 'list' in v:
            m8 = H_AMARK(st)
            if not u5(v['list'], d, s, st, H_PATH(pn, 'properties/list'), H_CHILD(cu, 'list', v['list'])):
                w6 = False
                H_ACUT(st, m8)
    if w6:
        H_DROP(st, m7)
    w7 = w6
    H_KWS(t3, 'properties', w6)
    H_EXIT(st, t3, w7)
    return w7

def u3(v, d, s, st, pn, cu):
    if d >= H_MAXD:
        H_DEEP()
    d += 1
    t4 = H_ENTER(st, x9, pn, cu)
    g2 = type(v) is dict
    w8 = True
    m9 = H_EMARK(st)
    if g2:
        if 'kind' in v:
            m10 = H_AMARK(st)
            if not u6(v['kind'], d, s, st, H_PATH(pn, 'properties/kind'), H_CHILD(cu, 'kind', v['kind'])):
                w8 = False
                H_ACUT(st, m10)
    if w8:
        H_DROP(st, m9)
    w9 = w8
    H_KWS(t4, 'properties', w8)
    H_EXIT(st, t4, w9)
    return w9

def u4(v, d, s, st, pn, cu):
    if d >= H_MAXD:
        H_DEEP()
    d += 1
    s = (*s, 'https://spike.example/island')
    t5 = H_ENTER(st, x11, pn, cu)
    w10 = True
    m11 = H_EMARK(st)
    m12 = H_AMARK(st)
    if not u7(v, d, s, st, H_PATH(pn, '$ref'), cu):
        w10 = False
        H_ACUT(st, m12)
    if w10:
        H_DROP(st, m11)
    w11 = w10
    H_KWS(t5, '$ref', w10)
    H_EXIT(st, t5, w11)
    return w11

def u5(v, d, s, st, pn, cu):
    if d >= H_MAXD:
        H_DEEP()
    d += 1
    s = (*s, 'https://spike.example/island')
    t6 = H_ENTER(st, x13, pn, cu)
    w12 = True
    m13 = H_EMARK(st)
    m14 = H_AMARK(st)
    if not u8(v, d, s, st, H_PATH(pn, '$ref'), cu):
        w12 = False
        H_ACUT(st, m14)
    if w12:
        H_DROP(st, m13)
    w13 = w12
    H_KWS(t6, '$ref', w12)
    H_EXIT(st, t6, w13)
    return w13

def u6(v, d, s, st, pn, cu):
    t7 = H_ENTER(st, x15, pn, cu)
    w14 = True
    m15 = H_EMARK(st)
    if not (type(v) is str and v == 'numbers'):
        H_ERR(st, x16, pn, cu, 'does not equal the required constant', {'allowedValue': 'numbers'})
        w14 = False
    if w14:
        H_DROP(st, m15)
    w15 = w14
    H_KWS(t7, 'const', w14)
    H_EXIT(st, t7, w15)
    return w15

def u7(v, d, s, st, pn, cu):
    if d >= H_MAXD:
        H_DEEP()
    d += 1
    s = (*s, 'https://spike.example/numberList')
    t8 = H_ENTER(st, x17, pn, cu)
    w16 = True
    m16 = H_EMARK(st)
    m17 = H_AMARK(st)
    if not u9(v, d, s, st, H_PATH(pn, '$ref'), cu):
        w16 = False
        H_ACUT(st, m17)
    if w16:
        H_DROP(st, m16)
    w17 = w16
    H_KWS(t8, '$ref', w16)
    H_EXIT(st, t8, w17)
    return w17

def u8(v, d, s, st, pn, cu):
    if d >= H_MAXD:
        H_DEEP()
    d += 1
    s = (*s, 'https://spike.example/stringList')
    t9 = H_ENTER(st, x21, pn, cu)
    w18 = True
    m18 = H_EMARK(st)
    m19 = H_AMARK(st)
    if not u9(v, d, s, st, H_PATH(pn, '$ref'), cu):
        w18 = False
        H_ACUT(st, m19)
    if w18:
        H_DROP(st, m18)
    w19 = w18
    H_KWS(t9, '$ref', w18)
    H_EXIT(st, t9, w19)
    return w19

def u9(v, d, s, st, pn, cu):
    if d >= H_MAXD:
        H_DEEP()
    d += 1
    s = (*s, 'https://spike.example/genericList')
    t10 = H_ENTER(st, x25, pn, cu)
    w20 = True
    m20 = H_EMARK(st)
    if type(v) is list:
        for b0 in range(0, len(v)):
            m21 = H_AMARK(st)
            if not H_FRAGE(st, T[0], s, d, H_PATH(pn, 'items'), H_CHILD(cu, b0, v[b0]), None):
                w20 = False
                H_ACUT(st, m21)
    if w20:
        H_DROP(st, m20)
    w21 = w20
    H_KWS(t10, 'items', w20)
    H_EXIT(st, t10, w21)
    return w21

def evaluate(v, st):
    try:
        return u0(v, 0, (), st, None, H_ROOT(v))
    except RecursionError:
        raise MaxDepthExceededError("compiled evaluation exceeded the interpreter's stack; reduce nesting or lower max_depth") from None
