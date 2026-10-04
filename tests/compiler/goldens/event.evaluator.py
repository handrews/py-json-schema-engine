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
x29 = X[29]
x30 = X[30]
k0 = ['object']
k1 = ['kind']
k2 = ['kind']
k3 = frozenset(('https://json-schema.org/draft/2020-12/vocab/applicator#additionalProperties', 'https://json-schema.org/draft/2020-12/vocab/applicator#patternProperties', 'https://json-schema.org/draft/2020-12/vocab/applicator#properties', 'https://json-schema.org/draft/2020-12/vocab/unevaluated#unevaluatedProperties'))
k4 = ['created', 'updated', 'deleted']
k5 = frozenset(('created', 'deleted', 'updated'))
k6 = ['object']
k7 = ['id', 'actor']
k8 = ['id', 'actor']
k9 = ['object']
k10 = ['createdAt']
k11 = ['createdAt']
k12 = ['string']
k13 = ['string']
k14 = ['string']
k15 = ['string']

def u0(v, d, s, st, pn, cu, ev):
    if d >= H_MAXD:
        H_DEEP()
    d += 1
    m0 = len(ev)
    t0 = H_ENTER(st, x0, pn, cu)
    g0 = type(v) is dict
    w0 = True
    w1 = True
    w2 = True
    w3 = True
    w4 = True
    m1 = H_EMARK(st)
    m2 = H_AMARK(st)
    m3 = len(ev)
    if not u1(v, d, s, st, H_PATH(pn, 'allOf/0'), cu, ev):
        w0 = False
        H_ACUT(st, m2)
        del ev[m3:]
    m4 = H_AMARK(st)
    m5 = len(ev)
    if not u2(v, d, s, st, H_PATH(pn, 'allOf/1'), cu, ev):
        w0 = False
        H_ACUT(st, m4)
        del ev[m5:]
    if w0:
        H_DROP(st, m1)
    m6 = H_EMARK(st)
    if g0:
        b0 = []
        if 'kind' in v:
            b0.append('kind')
            m7 = H_AMARK(st)
            if not u3(v['kind'], d, s, st, H_PATH(pn, 'properties/kind'), H_CHILD(cu, 'kind', v['kind'])):
                w1 = False
                H_ACUT(st, m7)
        if w1:
            ev.append(('https://json-schema.org/draft/2020-12/vocab/applicator#properties', b0))
    if w1:
        H_DROP(st, m6)
    m8 = H_EMARK(st)
    if not g0:
        H_ERR(st, x6, pn, cu, 'expected object, got ' + str(H_TPREV(v)), {'expected': k0, 'actual': H_ATYPE(v), 'value': v})
        w2 = False
    if w2:
        H_DROP(st, m8)
    m9 = H_EMARK(st)
    if g0 and 'kind' not in v:
        H_ERR(st, x7, pn, cu, 'missing required ' + str(H_LNAMES(H_MISS(v, k1), 'property', 'properties')), {'missing': H_MISS(v, k2)})
        w3 = False
    if w3:
        H_DROP(st, m9)
    m10 = H_EMARK(st)
    if g0:
        b1 = H_COVN(ev[m0:], k3)
        b2 = []
        b3 = []
        for b4 in v:
            if b4 not in b1:
                b2.append(b4)
                b3.append(b4)
        if b3:
            H_ERR(st, x8, pn, cu, 'unevaluated ' + str(H_LNAMES(b3, 'property', 'properties')) + ' not allowed', {'properties': b3})
            w4 = False
        if w4:
            ev.append(('https://json-schema.org/draft/2020-12/vocab/unevaluated#unevaluatedProperties', b2))
    if w4:
        H_DROP(st, m10)
    w5 = w0 and w1 and w2 and w3 and w4
    H_KWS(t0, 'allOf', w0, 'properties', w1, 'type', w2, 'required', w3, 'unevaluatedProperties', w4)
    H_EXIT(st, t0, w5)
    return w5

def u1(v, d, s, st, pn, cu, ev):
    if d >= H_MAXD:
        H_DEEP()
    d += 1
    t1 = H_ENTER(st, x9, pn, cu)
    w6 = True
    m11 = H_EMARK(st)
    m12 = H_AMARK(st)
    m13 = len(ev)
    if not u4(v, d, s, st, H_PATH(pn, '$ref'), cu, ev):
        w6 = False
        H_ACUT(st, m12)
        del ev[m13:]
    if w6:
        H_DROP(st, m11)
    w7 = w6
    H_KWS(t1, '$ref', w6)
    H_EXIT(st, t1, w7)
    return w7

def u2(v, d, s, st, pn, cu, ev):
    if d >= H_MAXD:
        H_DEEP()
    d += 1
    t2 = H_ENTER(st, x11, pn, cu)
    w8 = True
    m14 = H_EMARK(st)
    m15 = H_AMARK(st)
    m16 = len(ev)
    if not u5(v, d, s, st, H_PATH(pn, '$ref'), cu, ev):
        w8 = False
        H_ACUT(st, m15)
        del ev[m16:]
    if w8:
        H_DROP(st, m14)
    w9 = w8
    H_KWS(t2, '$ref', w8)
    H_EXIT(st, t2, w9)
    return w9

def u3(v, d, s, st, pn, cu):
    t3 = H_ENTER(st, x13, pn, cu)
    w10 = True
    m17 = H_EMARK(st)
    if not (type(v) is str and v in k5):
        H_ERR(st, x14, pn, cu, 'must be one of ["created", "updated", "deleted"], got ' + str(H_PREV(v)), {'allowedValues': k4, 'value': v})
        w10 = False
    if w10:
        H_DROP(st, m17)
    w11 = w10
    H_KWS(t3, 'enum', w10)
    H_EXIT(st, t3, w11)
    return w11

def u4(v, d, s, st, pn, cu, ev):
    if d >= H_MAXD:
        H_DEEP()
    d += 1
    t4 = H_ENTER(st, x15, pn, cu)
    g1 = type(v) is dict
    w12 = True
    w13 = True
    w14 = True
    m18 = H_EMARK(st)
    if g1:
        b5 = []
        if 'id' in v:
            b5.append('id')
            m19 = H_AMARK(st)
            if not u6(v['id'], d, s, st, H_PATH(pn, 'properties/id'), H_CHILD(cu, 'id', v['id'])):
                w12 = False
                H_ACUT(st, m19)
        if 'actor' in v:
            b5.append('actor')
            m20 = H_AMARK(st)
            if not u7(v['actor'], d, s, st, H_PATH(pn, 'properties/actor'), H_CHILD(cu, 'actor', v['actor'])):
                w12 = False
                H_ACUT(st, m20)
        if w12:
            ev.append(('https://json-schema.org/draft/2020-12/vocab/applicator#properties', b5))
    if w12:
        H_DROP(st, m18)
    m21 = H_EMARK(st)
    if not g1:
        H_ERR(st, x17, pn, cu, 'expected object, got ' + str(H_TPREV(v)), {'expected': k6, 'actual': H_ATYPE(v), 'value': v})
        w13 = False
    if w13:
        H_DROP(st, m21)
    m22 = H_EMARK(st)
    if g1 and ('id' not in v or 'actor' not in v):
        H_ERR(st, x18, pn, cu, 'missing required ' + str(H_LNAMES(H_MISS(v, k7), 'property', 'properties')), {'missing': H_MISS(v, k8)})
        w14 = False
    if w14:
        H_DROP(st, m22)
    w15 = w12 and w13 and w14
    H_KWS(t4, 'properties', w12, 'type', w13, 'required', w14)
    H_EXIT(st, t4, w15)
    return w15

def u5(v, d, s, st, pn, cu, ev):
    if d >= H_MAXD:
        H_DEEP()
    d += 1
    t5 = H_ENTER(st, x19, pn, cu)
    g2 = type(v) is dict
    w16 = True
    w17 = True
    w18 = True
    m23 = H_EMARK(st)
    if g2:
        b6 = []
        if 'createdAt' in v:
            b6.append('createdAt')
            m24 = H_AMARK(st)
            if not u8(v['createdAt'], d, s, st, H_PATH(pn, 'properties/createdAt'), H_CHILD(cu, 'createdAt', v['createdAt'])):
                w16 = False
                H_ACUT(st, m24)
        if 'updatedAt' in v:
            b6.append('updatedAt')
            m25 = H_AMARK(st)
            if not u9(v['updatedAt'], d, s, st, H_PATH(pn, 'properties/updatedAt'), H_CHILD(cu, 'updatedAt', v['updatedAt'])):
                w16 = False
                H_ACUT(st, m25)
        if w16:
            ev.append(('https://json-schema.org/draft/2020-12/vocab/applicator#properties', b6))
    if w16:
        H_DROP(st, m23)
    m26 = H_EMARK(st)
    if not g2:
        H_ERR(st, x21, pn, cu, 'expected object, got ' + str(H_TPREV(v)), {'expected': k9, 'actual': H_ATYPE(v), 'value': v})
        w17 = False
    if w17:
        H_DROP(st, m26)
    m27 = H_EMARK(st)
    if g2 and 'createdAt' not in v:
        H_ERR(st, x22, pn, cu, 'missing required ' + str(H_LNAMES(H_MISS(v, k10), 'property', 'properties')), {'missing': H_MISS(v, k11)})
        w18 = False
    if w18:
        H_DROP(st, m27)
    w19 = w16 and w17 and w18
    H_KWS(t5, 'properties', w16, 'type', w17, 'required', w18)
    H_EXIT(st, t5, w19)
    return w19

def u6(v, d, s, st, pn, cu):
    t6 = H_ENTER(st, x23, pn, cu)
    w20 = True
    m28 = H_EMARK(st)
    if type(v) is not str:
        H_ERR(st, x24, pn, cu, 'expected string, got ' + str(H_TPREV(v)), {'expected': k12, 'actual': H_ATYPE(v), 'value': v})
        w20 = False
    if w20:
        H_DROP(st, m28)
    w21 = w20
    H_KWS(t6, 'type', w20)
    H_EXIT(st, t6, w21)
    return w21

def u7(v, d, s, st, pn, cu):
    t7 = H_ENTER(st, x25, pn, cu)
    w22 = True
    m29 = H_EMARK(st)
    if type(v) is not str:
        H_ERR(st, x26, pn, cu, 'expected string, got ' + str(H_TPREV(v)), {'expected': k13, 'actual': H_ATYPE(v), 'value': v})
        w22 = False
    if w22:
        H_DROP(st, m29)
    w23 = w22
    H_KWS(t7, 'type', w22)
    H_EXIT(st, t7, w23)
    return w23

def u8(v, d, s, st, pn, cu):
    t8 = H_ENTER(st, x27, pn, cu)
    w24 = True
    m30 = H_EMARK(st)
    if type(v) is not str:
        H_ERR(st, x28, pn, cu, 'expected string, got ' + str(H_TPREV(v)), {'expected': k14, 'actual': H_ATYPE(v), 'value': v})
        w24 = False
    if w24:
        H_DROP(st, m30)
    w25 = w24
    H_KWS(t8, 'type', w24)
    H_EXIT(st, t8, w25)
    return w25

def u9(v, d, s, st, pn, cu):
    t9 = H_ENTER(st, x29, pn, cu)
    w26 = True
    m31 = H_EMARK(st)
    if type(v) is not str:
        H_ERR(st, x30, pn, cu, 'expected string, got ' + str(H_TPREV(v)), {'expected': k15, 'actual': H_ATYPE(v), 'value': v})
        w26 = False
    if w26:
        H_DROP(st, m31)
    w27 = w26
    H_KWS(t9, 'type', w26)
    H_EXIT(st, t9, w27)
    return w27

def evaluate(v, st):
    try:
        return u0(v, 0, (), st, None, H_ROOT(v), [])
    except RecursionError:
        raise MaxDepthExceededError("compiled evaluation exceeded the interpreter's stack; reduce nesting or lower max_depth") from None
