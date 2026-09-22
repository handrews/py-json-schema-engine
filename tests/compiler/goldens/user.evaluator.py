r0 = R.re['^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$']
r1 = R.re['^[0-9]{5}$']
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
k0 = frozenset(('address', 'email', 'id', 'name', 'role', 'tags'))
k1 = ['object']
k2 = ['integer']
k3 = ['string']
k4 = ['string']
k5 = ['admin', 'user', 'guest']
k6 = frozenset(('admin', 'guest', 'user'))
k7 = ['array']
k8 = ['object']
k9 = ['string']
k10 = ['string']
k11 = ['string']
k12 = ['string']

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
        if 'name' in v:
            m2 = H_AMARK(st)
            if not u2(v['name'], d, s, st, H_PATH(pn, 'properties/name'), H_CHILD(cu, 'name', v['name'])):
                w0 = False
                H_ACUT(st, m2)
        if 'email' in v:
            m3 = H_AMARK(st)
            if not u3(v['email'], d, s, st, H_PATH(pn, 'properties/email'), H_CHILD(cu, 'email', v['email'])):
                w0 = False
                H_ACUT(st, m3)
        if 'role' in v:
            m4 = H_AMARK(st)
            if not u4(v['role'], d, s, st, H_PATH(pn, 'properties/role'), H_CHILD(cu, 'role', v['role'])):
                w0 = False
                H_ACUT(st, m4)
        if 'tags' in v:
            m5 = H_AMARK(st)
            if not u5(v['tags'], d, s, st, H_PATH(pn, 'properties/tags'), H_CHILD(cu, 'tags', v['tags'])):
                w0 = False
                H_ACUT(st, m5)
        if 'address' in v:
            m6 = H_AMARK(st)
            if not u6(v['address'], d, s, st, H_PATH(pn, 'properties/address'), H_CHILD(cu, 'address', v['address'])):
                w0 = False
                H_ACUT(st, m6)
    if w0:
        H_DROP(st, m0)
    m7 = H_EMARK(st)
    if g0:
        for b0 in v:
            if b0 not in k0:
                m8 = H_AMARK(st)
                if not H_FALSE(st, x5, H_PATH(pn, 'additionalProperties'), H_CHILD(cu, b0, v[b0])):
                    w1 = False
                    H_ACUT(st, m8)
    if w1:
        H_DROP(st, m7)
    m9 = H_EMARK(st)
    if not g0:
        H_ERR(st, x6, pn, cu, 'expected object', {'expected': k1, 'actual': H_TYPE(v)})
        w2 = False
    if w2:
        H_DROP(st, m9)
    m10 = H_EMARK(st)
    if g0:
        if 'id' not in v:
            H_ERR(st, x7, pn, cu, "missing required property 'id'", {'missingProperty': 'id'})
            w3 = False
        if 'name' not in v:
            H_ERR(st, x7, pn, cu, "missing required property 'name'", {'missingProperty': 'name'})
            w3 = False
        if 'email' not in v:
            H_ERR(st, x7, pn, cu, "missing required property 'email'", {'missingProperty': 'email'})
            w3 = False
        if 'tags' not in v:
            H_ERR(st, x7, pn, cu, "missing required property 'tags'", {'missingProperty': 'tags'})
            w3 = False
    if w3:
        H_DROP(st, m10)
    w4 = w0 and w1 and w2 and w3
    H_KWS(t0, 'properties', w0, 'additionalProperties', w1, 'type', w2, 'required', w3)
    H_EXIT(st, t0, w4)
    return w4

def u1(v, d, s, st, pn, cu):
    t1 = H_ENTER(st, x8, pn, cu)
    w5 = True
    w6 = True
    m11 = H_EMARK(st)
    if not (type(v) is int or (type(v) is float and v.is_integer())):
        H_ERR(st, x9, pn, cu, 'expected integer', {'expected': k2, 'actual': H_TYPE(v)})
        w5 = False
    if w5:
        H_DROP(st, m11)
    m12 = H_EMARK(st)
    if (type(v) is int or type(v) is float) and (not v >= 1):
        H_ERR(st, x10, pn, cu, 'must be >= 1', {'limit': 1})
        w6 = False
    if w6:
        H_DROP(st, m12)
    w7 = w5 and w6
    H_KWS(t1, 'type', w5, 'minimum', w6)
    H_EXIT(st, t1, w7)
    return w7

def u2(v, d, s, st, pn, cu):
    t2 = H_ENTER(st, x11, pn, cu)
    w8 = True
    w9 = True
    w10 = True
    m13 = H_EMARK(st)
    if type(v) is not str:
        H_ERR(st, x12, pn, cu, 'expected string', {'expected': k3, 'actual': H_TYPE(v)})
        w8 = False
    if w8:
        H_DROP(st, m13)
    m14 = H_EMARK(st)
    if type(v) is str and (not len(v) <= 100):
        H_ERR(st, x13, pn, cu, 'must be at most 100 characters', {'limit': 100})
        w9 = False
    if w9:
        H_DROP(st, m14)
    m15 = H_EMARK(st)
    if type(v) is str and (not len(v) >= 1):
        H_ERR(st, x14, pn, cu, 'must be at least 1 characters', {'limit': 1})
        w10 = False
    if w10:
        H_DROP(st, m15)
    w11 = w8 and w9 and w10
    H_KWS(t2, 'type', w8, 'maxLength', w9, 'minLength', w10)
    H_EXIT(st, t2, w11)
    return w11

def u3(v, d, s, st, pn, cu):
    t3 = H_ENTER(st, x15, pn, cu)
    w12 = True
    w13 = True
    m16 = H_EMARK(st)
    if type(v) is str and r0.search(v) is None:
        H_ERR(st, x16, pn, cu, 'does not match pattern', {'pattern': '^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$'})
        w12 = False
    if w12:
        H_DROP(st, m16)
    m17 = H_EMARK(st)
    if type(v) is not str:
        H_ERR(st, x17, pn, cu, 'expected string', {'expected': k4, 'actual': H_TYPE(v)})
        w13 = False
    if w13:
        H_DROP(st, m17)
    w14 = w12 and w13
    H_KWS(t3, 'pattern', w12, 'type', w13)
    H_EXIT(st, t3, w14)
    return w14

def u4(v, d, s, st, pn, cu):
    t4 = H_ENTER(st, x18, pn, cu)
    w15 = True
    m18 = H_EMARK(st)
    if not (type(v) is str and v in k6):
        H_ERR(st, x19, pn, cu, 'not one of the allowed values', {'allowedValues': k5})
        w15 = False
    if w15:
        H_DROP(st, m18)
    w16 = w15
    H_KWS(t4, 'enum', w15)
    H_EXIT(st, t4, w16)
    return w16

def u5(v, d, s, st, pn, cu):
    if d >= H_MAXD:
        H_DEEP()
    d += 1
    t5 = H_ENTER(st, x20, pn, cu)
    w17 = True
    w18 = True
    w19 = True
    m19 = H_EMARK(st)
    if type(v) is list:
        for b1 in range(0, len(v)):
            m20 = H_AMARK(st)
            if not u7(v[b1], d, s, st, H_PATH(pn, 'items'), H_CHILD(cu, b1, v[b1])):
                w17 = False
                H_ACUT(st, m20)
    if w17:
        H_DROP(st, m19)
    m21 = H_EMARK(st)
    if type(v) is not list:
        H_ERR(st, x22, pn, cu, 'expected array', {'expected': k7, 'actual': H_TYPE(v)})
        w18 = False
    if w18:
        H_DROP(st, m21)
    m22 = H_EMARK(st)
    if type(v) is list and (not len(v) <= 10):
        H_ERR(st, x23, pn, cu, 'must have at most 10 items', {'limit': 10})
        w19 = False
    if w19:
        H_DROP(st, m22)
    w20 = w17 and w18 and w19
    H_KWS(t5, 'items', w17, 'type', w18, 'maxItems', w19)
    H_EXIT(st, t5, w20)
    return w20

def u6(v, d, s, st, pn, cu):
    if d >= H_MAXD:
        H_DEEP()
    d += 1
    t6 = H_ENTER(st, x24, pn, cu)
    g1 = type(v) is dict
    w21 = True
    w22 = True
    w23 = True
    m23 = H_EMARK(st)
    if g1:
        if 'street' in v:
            m24 = H_AMARK(st)
            if not u8(v['street'], d, s, st, H_PATH(pn, 'properties/street'), H_CHILD(cu, 'street', v['street'])):
                w21 = False
                H_ACUT(st, m24)
        if 'city' in v:
            m25 = H_AMARK(st)
            if not u9(v['city'], d, s, st, H_PATH(pn, 'properties/city'), H_CHILD(cu, 'city', v['city'])):
                w21 = False
                H_ACUT(st, m25)
        if 'zip' in v:
            m26 = H_AMARK(st)
            if not u10(v['zip'], d, s, st, H_PATH(pn, 'properties/zip'), H_CHILD(cu, 'zip', v['zip'])):
                w21 = False
                H_ACUT(st, m26)
    if w21:
        H_DROP(st, m23)
    m27 = H_EMARK(st)
    if not g1:
        H_ERR(st, x26, pn, cu, 'expected object', {'expected': k8, 'actual': H_TYPE(v)})
        w22 = False
    if w22:
        H_DROP(st, m27)
    m28 = H_EMARK(st)
    if g1:
        if 'street' not in v:
            H_ERR(st, x27, pn, cu, "missing required property 'street'", {'missingProperty': 'street'})
            w23 = False
        if 'city' not in v:
            H_ERR(st, x27, pn, cu, "missing required property 'city'", {'missingProperty': 'city'})
            w23 = False
    if w23:
        H_DROP(st, m28)
    w24 = w21 and w22 and w23
    H_KWS(t6, 'properties', w21, 'type', w22, 'required', w23)
    H_EXIT(st, t6, w24)
    return w24

def u7(v, d, s, st, pn, cu):
    t7 = H_ENTER(st, x28, pn, cu)
    w25 = True
    m29 = H_EMARK(st)
    if type(v) is not str:
        H_ERR(st, x29, pn, cu, 'expected string', {'expected': k9, 'actual': H_TYPE(v)})
        w25 = False
    if w25:
        H_DROP(st, m29)
    w26 = w25
    H_KWS(t7, 'type', w25)
    H_EXIT(st, t7, w26)
    return w26

def u8(v, d, s, st, pn, cu):
    t8 = H_ENTER(st, x30, pn, cu)
    w27 = True
    m30 = H_EMARK(st)
    if type(v) is not str:
        H_ERR(st, x31, pn, cu, 'expected string', {'expected': k10, 'actual': H_TYPE(v)})
        w27 = False
    if w27:
        H_DROP(st, m30)
    w28 = w27
    H_KWS(t8, 'type', w27)
    H_EXIT(st, t8, w28)
    return w28

def u9(v, d, s, st, pn, cu):
    t9 = H_ENTER(st, x32, pn, cu)
    w29 = True
    m31 = H_EMARK(st)
    if type(v) is not str:
        H_ERR(st, x33, pn, cu, 'expected string', {'expected': k11, 'actual': H_TYPE(v)})
        w29 = False
    if w29:
        H_DROP(st, m31)
    w30 = w29
    H_KWS(t9, 'type', w29)
    H_EXIT(st, t9, w30)
    return w30

def u10(v, d, s, st, pn, cu):
    t10 = H_ENTER(st, x34, pn, cu)
    w31 = True
    w32 = True
    m32 = H_EMARK(st)
    if type(v) is str and r1.search(v) is None:
        H_ERR(st, x35, pn, cu, 'does not match pattern', {'pattern': '^[0-9]{5}$'})
        w31 = False
    if w31:
        H_DROP(st, m32)
    m33 = H_EMARK(st)
    if type(v) is not str:
        H_ERR(st, x36, pn, cu, 'expected string', {'expected': k12, 'actual': H_TYPE(v)})
        w32 = False
    if w32:
        H_DROP(st, m33)
    w33 = w31 and w32
    H_KWS(t10, 'pattern', w31, 'type', w32)
    H_EXIT(st, t10, w33)
    return w33

def evaluate(v, st):
    try:
        return u0(v, 0, (), st, None, H_ROOT(v))
    except RecursionError:
        raise MaxDepthExceededError("compiled evaluation exceeded the interpreter's stack; reduce nesting or lower max_depth") from None
