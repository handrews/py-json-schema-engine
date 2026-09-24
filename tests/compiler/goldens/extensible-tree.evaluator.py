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
x31 = X[31]
x32 = X[32]
x33 = X[33]
x34 = X[34]
x35 = X[35]
x36 = X[36]
x37 = X[37]
x38 = X[38]
x39 = X[39]
x40 = X[40]
x41 = X[41]
x42 = X[42]
x43 = X[43]
x44 = X[44]
x45 = X[45]
x46 = X[46]
x47 = X[47]
x48 = X[48]
x49 = X[49]
k0 = frozenset(('https://json-schema.org/draft/2020-12/vocab/applicator#additionalProperties', 'https://json-schema.org/draft/2020-12/vocab/applicator#patternProperties', 'https://json-schema.org/draft/2020-12/vocab/applicator#properties', 'https://json-schema.org/draft/2020-12/vocab/unevaluated#unevaluatedProperties'))
k1 = frozenset(('https://json-schema.org/draft/2020-12/vocab/applicator#additionalProperties', 'https://json-schema.org/draft/2020-12/vocab/applicator#patternProperties', 'https://json-schema.org/draft/2020-12/vocab/applicator#properties', 'https://json-schema.org/draft/2020-12/vocab/unevaluated#unevaluatedProperties'))
k2 = ['object']
k3 = ['string']
k4 = ['object']
k5 = ['number']
k6 = ['string']
k7 = ['array']
k8 = ['string']
k9 = ['array']

def u0(v, d, s, st, pn, cu):
    if d >= H_MAXD:
        H_DEEP()
    d += 1
    t0 = H_ENTER(st, x0, pn, cu)
    g0 = type(v) is dict
    w0 = True
    m0 = H_EMARK(st)
    if g0:
        if 'taxonomy' in v:
            m1 = H_AMARK(st)
            if not u1(v['taxonomy'], d, s, st, H_PATH(pn, 'properties/taxonomy'), H_CHILD(cu, 'taxonomy', v['taxonomy'])):
                w0 = False
                H_ACUT(st, m1)
        if 'phylogeny' in v:
            m2 = H_AMARK(st)
            if not u2(v['phylogeny'], d, s, st, H_PATH(pn, 'properties/phylogeny'), H_CHILD(cu, 'phylogeny', v['phylogeny'])):
                w0 = False
                H_ACUT(st, m2)
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
    m3 = H_EMARK(st)
    m4 = H_AMARK(st)
    if not u3(v, d, s, st, H_PATH(pn, '$ref'), cu, []):
        w2 = False
        H_ACUT(st, m4)
    if w2:
        H_DROP(st, m3)
    w3 = w2
    H_KWS(t1, '$ref', w2)
    H_EXIT(st, t1, w3)
    return w3

def u2(v, d, s, st, pn, cu):
    if d >= H_MAXD:
        H_DEEP()
    d += 1
    t2 = H_ENTER(st, x5, pn, cu)
    w4 = True
    m5 = H_EMARK(st)
    m6 = H_AMARK(st)
    if not u4(v, d, s, st, H_PATH(pn, '$ref'), cu, []):
        w4 = False
        H_ACUT(st, m6)
    if w4:
        H_DROP(st, m5)
    w5 = w4
    H_KWS(t2, '$ref', w4)
    H_EXIT(st, t2, w5)
    return w5

def u3(v, d, s, st, pn, cu, ev):
    if d >= H_MAXD:
        H_DEEP()
    d += 1
    m7 = len(ev)
    t3 = H_ENTER(st, x7, pn, cu)
    g1 = type(v) is dict
    w6 = True
    w7 = True
    w8 = True
    w9 = True
    m8 = H_EMARK(st)
    m9 = H_AMARK(st)
    m10 = len(ev)
    if not u5(v, d, s, st, H_PATH(pn, '$ref'), cu, ev):
        w6 = False
        H_ACUT(st, m9)
        del ev[m10:]
    if w6:
        H_DROP(st, m8)
    m11 = H_EMARK(st)
    if g1:
        b0 = []
        if 'rank' in v:
            b0.append('rank')
            m12 = H_AMARK(st)
            if not u6(v['rank'], d, s, st, H_PATH(pn, 'properties/rank'), H_CHILD(cu, 'rank', v['rank'])):
                w7 = False
                H_ACUT(st, m12)
        if w7:
            ev.append(('https://json-schema.org/draft/2020-12/vocab/applicator#properties', b0))
    if w7:
        H_DROP(st, m11)
    m13 = H_EMARK(st)
    if g1:
        if 'rank' not in v:
            H_ERR(st, x12, pn, cu, "missing required property 'rank'", {'missingProperty': 'rank'})
            w8 = False
    if w8:
        H_DROP(st, m13)
    m14 = H_EMARK(st)
    if g1:
        b1 = H_COVN(ev[m7:], k0)
        b2 = []
        for b3 in v:
            if b3 not in b1:
                b2.append(b3)
                m15 = H_AMARK(st)
                if not H_FALSE(st, x14, H_PATH(pn, 'unevaluatedProperties'), H_CHILD(cu, b3, v[b3])):
                    w9 = False
                    H_ACUT(st, m15)
        if w9:
            ev.append(('https://json-schema.org/draft/2020-12/vocab/unevaluated#unevaluatedProperties', b2))
    if w9:
        H_DROP(st, m14)
    w10 = w6 and w7 and w8 and w9
    H_KWS(t3, '$ref', w6, 'properties', w7, 'required', w8, 'unevaluatedProperties', w9)
    H_EXIT(st, t3, w10)
    return w10

def u4(v, d, s, st, pn, cu, ev):
    if d >= H_MAXD:
        H_DEEP()
    d += 1
    m16 = len(ev)
    t4 = H_ENTER(st, x15, pn, cu)
    g2 = type(v) is dict
    w11 = True
    w12 = True
    w13 = True
    m17 = H_EMARK(st)
    m18 = H_AMARK(st)
    m19 = len(ev)
    if not u7(v, d, s, st, H_PATH(pn, '$ref'), cu, ev):
        w11 = False
        H_ACUT(st, m18)
        del ev[m19:]
    if w11:
        H_DROP(st, m17)
    m20 = H_EMARK(st)
    if g2:
        b4 = []
        if 'support' in v:
            b4.append('support')
            m21 = H_AMARK(st)
            if not u8(v['support'], d, s, st, H_PATH(pn, 'properties/support'), H_CHILD(cu, 'support', v['support'])):
                w12 = False
                H_ACUT(st, m21)
        if w12:
            ev.append(('https://json-schema.org/draft/2020-12/vocab/applicator#properties', b4))
    if w12:
        H_DROP(st, m20)
    m22 = H_EMARK(st)
    if g2:
        b5 = H_COVN(ev[m16:], k1)
        b6 = []
        for b7 in v:
            if b7 not in b5:
                b6.append(b7)
                m23 = H_AMARK(st)
                if not H_FALSE(st, x21, H_PATH(pn, 'unevaluatedProperties'), H_CHILD(cu, b7, v[b7])):
                    w13 = False
                    H_ACUT(st, m23)
        if w13:
            ev.append(('https://json-schema.org/draft/2020-12/vocab/unevaluated#unevaluatedProperties', b6))
    if w13:
        H_DROP(st, m22)
    w14 = w11 and w12 and w13
    H_KWS(t4, '$ref', w11, 'properties', w12, 'unevaluatedProperties', w13)
    H_EXIT(st, t4, w14)
    return w14

def u5(v, d, s, st, pn, cu, ev):
    if d >= H_MAXD:
        H_DEEP()
    d += 1
    t5 = H_ENTER(st, x22, pn, cu)
    g3 = type(v) is dict
    w15 = True
    w16 = True
    m24 = H_EMARK(st)
    if g3:
        b8 = []
        if 'name' in v:
            b8.append('name')
            m25 = H_AMARK(st)
            if not u9(v['name'], d, s, st, H_PATH(pn, 'properties/name'), H_CHILD(cu, 'name', v['name'])):
                w15 = False
                H_ACUT(st, m25)
        if 'children' in v:
            b8.append('children')
            m26 = H_AMARK(st)
            if not u10(v['children'], d, s, st, H_PATH(pn, 'properties/children'), H_CHILD(cu, 'children', v['children'])):
                w15 = False
                H_ACUT(st, m26)
        if w15:
            ev.append(('https://json-schema.org/draft/2020-12/vocab/applicator#properties', b8))
    if w15:
        H_DROP(st, m24)
    m27 = H_EMARK(st)
    if not g3:
        H_ERR(st, x26, pn, cu, 'expected object', {'expected': k2, 'actual': H_TYPE(v)})
        w16 = False
    if w16:
        H_DROP(st, m27)
    w17 = w15 and w16
    H_KWS(t5, 'properties', w15, 'type', w16)
    H_EXIT(st, t5, w17)
    return w17

def u6(v, d, s, st, pn, cu):
    t6 = H_ENTER(st, x27, pn, cu)
    w18 = True
    m28 = H_EMARK(st)
    if type(v) is not str:
        H_ERR(st, x28, pn, cu, 'expected string', {'expected': k3, 'actual': H_TYPE(v)})
        w18 = False
    if w18:
        H_DROP(st, m28)
    w19 = w18
    H_KWS(t6, 'type', w18)
    H_EXIT(st, t6, w19)
    return w19

def u7(v, d, s, st, pn, cu, ev):
    if d >= H_MAXD:
        H_DEEP()
    d += 1
    t7 = H_ENTER(st, x29, pn, cu)
    g4 = type(v) is dict
    w20 = True
    w21 = True
    m29 = H_EMARK(st)
    if g4:
        b9 = []
        if 'name' in v:
            b9.append('name')
            m30 = H_AMARK(st)
            if not u11(v['name'], d, s, st, H_PATH(pn, 'properties/name'), H_CHILD(cu, 'name', v['name'])):
                w20 = False
                H_ACUT(st, m30)
        if 'children' in v:
            b9.append('children')
            m31 = H_AMARK(st)
            if not u12(v['children'], d, s, st, H_PATH(pn, 'properties/children'), H_CHILD(cu, 'children', v['children'])):
                w20 = False
                H_ACUT(st, m31)
        if w20:
            ev.append(('https://json-schema.org/draft/2020-12/vocab/applicator#properties', b9))
    if w20:
        H_DROP(st, m29)
    m32 = H_EMARK(st)
    if not g4:
        H_ERR(st, x33, pn, cu, 'expected object', {'expected': k4, 'actual': H_TYPE(v)})
        w21 = False
    if w21:
        H_DROP(st, m32)
    w22 = w20 and w21
    H_KWS(t7, 'properties', w20, 'type', w21)
    H_EXIT(st, t7, w22)
    return w22

def u8(v, d, s, st, pn, cu):
    t8 = H_ENTER(st, x34, pn, cu)
    w23 = True
    m33 = H_EMARK(st)
    if not (type(v) is int or type(v) is float):
        H_ERR(st, x35, pn, cu, 'expected number', {'expected': k5, 'actual': H_TYPE(v)})
        w23 = False
    if w23:
        H_DROP(st, m33)
    w24 = w23
    H_KWS(t8, 'type', w23)
    H_EXIT(st, t8, w24)
    return w24

def u9(v, d, s, st, pn, cu):
    t9 = H_ENTER(st, x36, pn, cu)
    w25 = True
    m34 = H_EMARK(st)
    if type(v) is not str:
        H_ERR(st, x37, pn, cu, 'expected string', {'expected': k6, 'actual': H_TYPE(v)})
        w25 = False
    if w25:
        H_DROP(st, m34)
    w26 = w25
    H_KWS(t9, 'type', w25)
    H_EXIT(st, t9, w26)
    return w26

def u10(v, d, s, st, pn, cu):
    if d >= H_MAXD:
        H_DEEP()
    d += 1
    t10 = H_ENTER(st, x38, pn, cu)
    w27 = True
    w28 = True
    m35 = H_EMARK(st)
    if type(v) is list:
        for b10 in range(0, len(v)):
            m36 = H_AMARK(st)
            if not u13(v[b10], d, s, st, H_PATH(pn, 'items'), H_CHILD(cu, b10, v[b10])):
                w27 = False
                H_ACUT(st, m36)
    if w27:
        H_DROP(st, m35)
    m37 = H_EMARK(st)
    if type(v) is not list:
        H_ERR(st, x40, pn, cu, 'expected array', {'expected': k7, 'actual': H_TYPE(v)})
        w28 = False
    if w28:
        H_DROP(st, m37)
    w29 = w27 and w28
    H_KWS(t10, 'items', w27, 'type', w28)
    H_EXIT(st, t10, w29)
    return w29

def u11(v, d, s, st, pn, cu):
    t11 = H_ENTER(st, x41, pn, cu)
    w30 = True
    m38 = H_EMARK(st)
    if type(v) is not str:
        H_ERR(st, x42, pn, cu, 'expected string', {'expected': k8, 'actual': H_TYPE(v)})
        w30 = False
    if w30:
        H_DROP(st, m38)
    w31 = w30
    H_KWS(t11, 'type', w30)
    H_EXIT(st, t11, w31)
    return w31

def u12(v, d, s, st, pn, cu):
    if d >= H_MAXD:
        H_DEEP()
    d += 1
    t12 = H_ENTER(st, x43, pn, cu)
    w32 = True
    w33 = True
    m39 = H_EMARK(st)
    if type(v) is list:
        for b11 in range(0, len(v)):
            m40 = H_AMARK(st)
            if not u14(v[b11], d, s, st, H_PATH(pn, 'items'), H_CHILD(cu, b11, v[b11])):
                w32 = False
                H_ACUT(st, m40)
    if w32:
        H_DROP(st, m39)
    m41 = H_EMARK(st)
    if type(v) is not list:
        H_ERR(st, x45, pn, cu, 'expected array', {'expected': k9, 'actual': H_TYPE(v)})
        w33 = False
    if w33:
        H_DROP(st, m41)
    w34 = w32 and w33
    H_KWS(t12, 'items', w32, 'type', w33)
    H_EXIT(st, t12, w34)
    return w34

def u13(v, d, s, st, pn, cu):
    if d >= H_MAXD:
        H_DEEP()
    d += 1
    t13 = H_ENTER(st, x46, pn, cu)
    w35 = True
    m42 = H_EMARK(st)
    m43 = H_AMARK(st)
    if not u3(v, d, s, st, H_PATH(pn, '$dynamicRef'), cu, []):
        w35 = False
        H_ACUT(st, m43)
    if w35:
        H_DROP(st, m42)
    w36 = w35
    H_KWS(t13, '$dynamicRef', w35)
    H_EXIT(st, t13, w36)
    return w36

def u14(v, d, s, st, pn, cu):
    if d >= H_MAXD:
        H_DEEP()
    d += 1
    t14 = H_ENTER(st, x48, pn, cu)
    w37 = True
    m44 = H_EMARK(st)
    m45 = H_AMARK(st)
    if not u4(v, d, s, st, H_PATH(pn, '$dynamicRef'), cu, []):
        w37 = False
        H_ACUT(st, m45)
    if w37:
        H_DROP(st, m44)
    w38 = w37
    H_KWS(t14, '$dynamicRef', w37)
    H_EXIT(st, t14, w38)
    return w38

def evaluate(v, st):
    try:
        return u0(v, 0, (), st, None, H_ROOT(v))
    except RecursionError:
        raise MaxDepthExceededError("compiled evaluation exceeded the interpreter's stack; reduce nesting or lower max_depth") from None
