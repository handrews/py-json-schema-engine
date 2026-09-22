def u0(v, d, s):
    g0 = type(v) is dict
    if g0:
        if 'p' in v:
            t0 = v['p']
            if type(t0) is not str:
                return False
    return True

def validate(v):
    try:
        return u0(v, 0, ())
    except RecursionError:
        raise MaxDepthExceededError("compiled evaluation exceeded the interpreter's stack; reduce nesting or lower max_depth") from None
