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
k0 = ['object']
k1 = ['string']
k2 = ['string']
k3 = ['string']
k4 = ['string']

def u0(v, d, s, st, pn, cu):
    if d >= H_MAXD:
        H_DEEP()
    d += 1
    t0 = H_ENTER(st, x0, pn, cu)
    g0 = type(v) is dict
    w0 = True
    w1 = True
    w2 = True
    w3 = True
    m0 = H_EMARK(st)
    if g0:
        if 'id' in v:
            m1 = H_AMARK(st)
            if not u1(v['id'], d, s, st, H_PATH(pn, 'properties/id'), H_CHILD(cu, 'id', v['id'])):
                w0 = False
                H_ACUT(st, m1)
        if 'displayName' in v:
            m2 = H_AMARK(st)
            if not u2(v['displayName'], d, s, st, H_PATH(pn, 'properties/displayName'), H_CHILD(cu, 'displayName', v['displayName'])):
                w0 = False
                H_ACUT(st, m2)
        if 'bio' in v:
            m3 = H_AMARK(st)
            if not u3(v['bio'], d, s, st, H_PATH(pn, 'properties/bio'), H_CHILD(cu, 'bio', v['bio'])):
                w0 = False
                H_ACUT(st, m3)
        if 'createdAt' in v:
            m4 = H_AMARK(st)
            if not u4(v['createdAt'], d, s, st, H_PATH(pn, 'properties/createdAt'), H_CHILD(cu, 'createdAt', v['createdAt'])):
                w0 = False
                H_ACUT(st, m4)
    if w0:
        H_DROP(st, m0)
    m5 = H_EMARK(st)
    if not g0:
        H_ERR(st, x4, pn, cu, 'expected object', {'expected': k0, 'actual': H_TYPE(v)})
        w1 = False
    if w1:
        H_DROP(st, m5)
    m6 = H_EMARK(st)
    if g0:
        if 'id' not in v:
            H_ERR(st, x5, pn, cu, "missing required property 'id'", {'missingProperty': 'id'})
            w2 = False
    if w2:
        H_DROP(st, m6)
    m7 = H_EMARK(st)
    H_ANN(st, x6, pn, cu, 'User profile')
    if w3:
        H_DROP(st, m7)
    w4 = w0 and w1 and w2 and w3
    H_KWS(t0, 'properties', w0, 'type', w1, 'required', w2, 'title', w3)
    H_EXIT(st, t0, w4)
    return w4

def u1(v, d, s, st, pn, cu):
    t1 = H_ENTER(st, x7, pn, cu)
    w5 = True
    w6 = True
    w7 = True
    m8 = H_EMARK(st)
    if type(v) is not str:
        H_ERR(st, x8, pn, cu, 'expected string', {'expected': k1, 'actual': H_TYPE(v)})
        w5 = False
    if w5:
        H_DROP(st, m8)
    m9 = H_EMARK(st)
    H_ANN(st, x9, pn, cu, 'Identifier')
    if w6:
        H_DROP(st, m9)
    m10 = H_EMARK(st)
    H_ANN(st, x10, pn, cu, True)
    if w7:
        H_DROP(st, m10)
    w8 = w5 and w6 and w7
    H_KWS(t1, 'type', w5, 'title', w6, 'readOnly', w7)
    H_EXIT(st, t1, w8)
    return w8

def u2(v, d, s, st, pn, cu):
    t2 = H_ENTER(st, x11, pn, cu)
    w9 = True
    w10 = True
    w11 = True
    m11 = H_EMARK(st)
    if type(v) is not str:
        H_ERR(st, x12, pn, cu, 'expected string', {'expected': k2, 'actual': H_TYPE(v)})
        w9 = False
    if w9:
        H_DROP(st, m11)
    m12 = H_EMARK(st)
    H_ANN(st, x13, pn, cu, 'Display name')
    if w10:
        H_DROP(st, m12)
    m13 = H_EMARK(st)
    H_ANN(st, x14, pn, cu, '')
    if w11:
        H_DROP(st, m13)
    w12 = w9 and w10 and w11
    H_KWS(t2, 'type', w9, 'title', w10, 'default', w11)
    H_EXIT(st, t2, w12)
    return w12

def u3(v, d, s, st, pn, cu):
    t3 = H_ENTER(st, x15, pn, cu)
    w13 = True
    w14 = True
    w15 = True
    m14 = H_EMARK(st)
    if type(v) is not str:
        H_ERR(st, x16, pn, cu, 'expected string', {'expected': k3, 'actual': H_TYPE(v)})
        w13 = False
    if w13:
        H_DROP(st, m14)
    m15 = H_EMARK(st)
    H_ANN(st, x17, pn, cu, 'Biography')
    if w14:
        H_DROP(st, m15)
    m16 = H_EMARK(st)
    H_ANN(st, x18, pn, cu, '')
    if w15:
        H_DROP(st, m16)
    w16 = w13 and w14 and w15
    H_KWS(t3, 'type', w13, 'title', w14, 'default', w15)
    H_EXIT(st, t3, w16)
    return w16

def u4(v, d, s, st, pn, cu):
    t4 = H_ENTER(st, x19, pn, cu)
    w17 = True
    w18 = True
    w19 = True
    m17 = H_EMARK(st)
    if type(v) is not str:
        H_ERR(st, x20, pn, cu, 'expected string', {'expected': k4, 'actual': H_TYPE(v)})
        w17 = False
    if w17:
        H_DROP(st, m17)
    m18 = H_EMARK(st)
    H_ANN(st, x21, pn, cu, 'Created')
    if w18:
        H_DROP(st, m18)
    m19 = H_EMARK(st)
    H_ANN(st, x22, pn, cu, True)
    if w19:
        H_DROP(st, m19)
    w20 = w17 and w18 and w19
    H_KWS(t4, 'type', w17, 'title', w18, 'readOnly', w19)
    H_EXIT(st, t4, w20)
    return w20

def evaluate(v, st):
    try:
        return u0(v, 0, (), st, None, H_ROOT(v))
    except RecursionError:
        raise MaxDepthExceededError("compiled evaluation exceeded the interpreter's stack; reduce nesting or lower max_depth") from None
