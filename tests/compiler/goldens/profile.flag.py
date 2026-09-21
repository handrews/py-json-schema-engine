def u0(v, d, s):
    g0 = type(v) is dict
    if g0:
        if 'id' in v:
            t0 = v['id']
            if type(t0) is not str:
                return False
        if 'displayName' in v:
            t1 = v['displayName']
            if type(t1) is not str:
                return False
        if 'bio' in v:
            t2 = v['bio']
            if type(t2) is not str:
                return False
        if 'createdAt' in v:
            t3 = v['createdAt']
            if type(t3) is not str:
                return False
    if not g0:
        return False
    if g0:
        if 'id' not in v:
            return False
    return True

def validate(v):
    try:
        return u0(v, 0, ())
    except RecursionError:
        raise MaxDepthExceededError("compiled evaluation exceeded the interpreter's stack; reduce nesting or lower max_depth") from None
