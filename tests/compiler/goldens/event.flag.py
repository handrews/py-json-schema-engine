k0 = frozenset(('created', 'deleted', 'updated'))
k1 = frozenset(('actor', 'createdAt', 'id', 'kind', 'updatedAt'))

def u0(v, d, s):
    g0 = type(v) is dict
    if g0:
        if 'id' in v:
            t0 = v['id']
            if type(t0) is not str:
                return False
        if 'actor' in v:
            t1 = v['actor']
            if type(t1) is not str:
                return False
    if not g0:
        return False
    if g0:
        if 'id' not in v:
            return False
        if 'actor' not in v:
            return False
    if g0:
        if 'createdAt' in v:
            t2 = v['createdAt']
            if type(t2) is not str:
                return False
        if 'updatedAt' in v:
            t3 = v['updatedAt']
            if type(t3) is not str:
                return False
    if not g0:
        return False
    if g0:
        if 'createdAt' not in v:
            return False
    if g0:
        if 'kind' in v:
            t4 = v['kind']
            if not (type(t4) is str and t4 in k0):
                return False
    if not g0:
        return False
    if g0:
        if 'kind' not in v:
            return False
    if g0:
        for b0 in v:
            if b0 not in k1:
                return False
    return True

def validate(v):
    try:
        return u0(v, 0, ())
    except RecursionError:
        raise MaxDepthExceededError("compiled evaluation exceeded the interpreter's stack; reduce nesting or lower max_depth") from None
