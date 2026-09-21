def u0(v, d, s):
    g0 = type(v) is dict
    if g0:
        if 'a' in v:
            t0 = v['a']
            if type(t0) is not str:
                return False
    if g0:
        for b0 in v:
            if not (type(b0) is str and b0 == 'a'):
                return False
    return True

def validate(v):
    try:
        return u0(v, 0, ())
    except RecursionError:
        raise MaxDepthExceededError("compiled evaluation exceeded the interpreter's stack; reduce nesting or lower max_depth") from None
