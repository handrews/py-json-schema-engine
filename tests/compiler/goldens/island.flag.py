def u0(v, d, s):
    if d >= H_MAXD:
        H_DEEP()
    d += 1
    s = (*s, 'https://spike.example/island')
    g0 = type(v) is dict
    if g0:
        if 'p' in v:
            if not H_FRAG(T[0], v['p'], s, d):
                return False
    return True

def validate(v):
    try:
        return u0(v, 0, ())
    except RecursionError:
        raise MaxDepthExceededError("compiled evaluation exceeded the interpreter's stack; reduce nesting or lower max_depth") from None
