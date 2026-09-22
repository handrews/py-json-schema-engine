def u0(v, d, s):
    if d >= H_MAXD:
        H_DEEP()
    d += 1
    s = (*s, 'https://spike.example/island')
    if u3(v, d, s):
        if not u1(v, d, s):
            return False
    elif not u2(v, d, s):
        return False
    return True

def u1(v, d, s):
    if d >= H_MAXD:
        H_DEEP()
    d += 1
    s = (*s, 'https://spike.example/island')
    g0 = type(v) is dict
    if g0:
        if 'list' in v:
            if not u4(v['list'], d, s):
                return False
    return True

def u2(v, d, s):
    if d >= H_MAXD:
        H_DEEP()
    d += 1
    s = (*s, 'https://spike.example/island')
    g1 = type(v) is dict
    if g1:
        if 'list' in v:
            if not u5(v['list'], d, s):
                return False
    return True

def u3(v, d, s):
    g2 = type(v) is dict
    if g2:
        if 'kind' in v:
            t0 = v['kind']
            if not (type(t0) is str and t0 == 'numbers'):
                return False
    return True

def u4(v, d, s):
    if d >= H_MAXD:
        H_DEEP()
    d += 1
    s = (*s, 'https://spike.example/island')
    if not u6(v, d, s):
        return False
    return True

def u5(v, d, s):
    if d >= H_MAXD:
        H_DEEP()
    d += 1
    s = (*s, 'https://spike.example/island')
    if not u7(v, d, s):
        return False
    return True

def u6(v, d, s):
    if d >= H_MAXD:
        H_DEEP()
    d += 1
    s = (*s, 'https://spike.example/numberList')
    if not u8(v, d, s):
        return False
    return True

def u7(v, d, s):
    if d >= H_MAXD:
        H_DEEP()
    d += 1
    s = (*s, 'https://spike.example/stringList')
    if not u8(v, d, s):
        return False
    return True

def u8(v, d, s):
    if d >= H_MAXD:
        H_DEEP()
    d += 1
    s = (*s, 'https://spike.example/genericList')
    if type(v) is list:
        for b0 in range(0, len(v)):
            if not H_FRAG(T[0], v[b0], s, d):
                return False
    return True

def validate(v):
    try:
        return u0(v, 0, ())
    except RecursionError:
        raise MaxDepthExceededError("compiled evaluation exceeded the interpreter's stack; reduce nesting or lower max_depth") from None
