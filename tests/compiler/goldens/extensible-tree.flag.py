k0 = frozenset(('children', 'name', 'rank'))
k1 = frozenset(('children', 'name', 'support'))

def u0(v, d, s):
    if d >= H_MAXD:
        H_DEEP()
    d += 1
    g0 = type(v) is dict
    if g0:
        if 'taxonomy' in v:
            t0 = v['taxonomy']
            if not u1(t0, d, s):
                return False
        if 'phylogeny' in v:
            t1 = v['phylogeny']
            if not u2(t1, d, s):
                return False
    return True

def u1(v, d, s):
    if d >= H_MAXD:
        H_DEEP()
    d += 1
    g1 = type(v) is dict
    if g1:
        if 'name' in v:
            t2 = v['name']
            if type(t2) is not str:
                return False
        if 'children' in v:
            t3 = v['children']
            if type(t3) is list:
                for b0 in range(0, len(t3)):
                    t4 = t3[b0]
                    if not u1(t4, d, s):
                        return False
            if type(t3) is not list:
                return False
    if not g1:
        return False
    if g1:
        if 'rank' in v:
            t5 = v['rank']
            if type(t5) is not str:
                return False
    if g1:
        if 'rank' not in v:
            return False
    if g1:
        for b1 in v:
            if b1 not in k0:
                return False
    return True

def u2(v, d, s):
    if d >= H_MAXD:
        H_DEEP()
    d += 1
    g2 = type(v) is dict
    if g2:
        if 'name' in v:
            t6 = v['name']
            if type(t6) is not str:
                return False
        if 'children' in v:
            t7 = v['children']
            if type(t7) is list:
                for b2 in range(0, len(t7)):
                    t8 = t7[b2]
                    if not u2(t8, d, s):
                        return False
            if type(t7) is not list:
                return False
    if not g2:
        return False
    if g2:
        if 'support' in v:
            t9 = v['support']
            if not (type(t9) is int or type(t9) is float):
                return False
    if g2:
        for b3 in v:
            if b3 not in k1:
                return False
    return True

def validate(v):
    try:
        return u0(v, 0, ())
    except RecursionError:
        raise MaxDepthExceededError("compiled evaluation exceeded the interpreter's stack; reduce nesting or lower max_depth") from None
