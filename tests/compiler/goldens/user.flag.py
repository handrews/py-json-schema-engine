r0 = R.re['^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$']
r1 = R.re['^[0-9]{5}$']
k0 = frozenset(('admin', 'guest', 'user'))
k1 = frozenset(('address', 'email', 'id', 'name', 'role', 'tags'))

def u0(v, d, s):
    g0 = type(v) is dict
    if g0:
        if 'id' in v:
            t0 = v['id']
            if not (type(t0) is int or (type(t0) is float and t0.is_integer())):
                return False
            if (type(t0) is int or type(t0) is float) and (not t0 >= 1):
                return False
        if 'name' in v:
            t1 = v['name']
            if type(t1) is not str:
                return False
            if type(t1) is str and (not len(t1) <= 100):
                return False
            if type(t1) is str and (not len(t1) >= 1):
                return False
        if 'email' in v:
            t2 = v['email']
            if type(t2) is str and r0.search(t2) is None:
                return False
            if type(t2) is not str:
                return False
        if 'role' in v:
            t3 = v['role']
            if not (type(t3) is str and t3 in k0):
                return False
        if 'tags' in v:
            t4 = v['tags']
            if type(t4) is list:
                for b0 in range(0, len(t4)):
                    t5 = t4[b0]
                    if type(t5) is not str:
                        return False
            if type(t4) is not list:
                return False
            if type(t4) is list and (not len(t4) <= 10):
                return False
        if 'address' in v:
            t6 = v['address']
            g1 = type(t6) is dict
            if g1:
                if 'street' in t6:
                    t7 = t6['street']
                    if type(t7) is not str:
                        return False
                if 'city' in t6:
                    t8 = t6['city']
                    if type(t8) is not str:
                        return False
                if 'zip' in t6:
                    t9 = t6['zip']
                    if type(t9) is str and r1.search(t9) is None:
                        return False
                    if type(t9) is not str:
                        return False
            if not g1:
                return False
            if g1:
                if 'street' not in t6:
                    return False
                if 'city' not in t6:
                    return False
    if g0:
        for b1 in v:
            if b1 not in k1:
                return False
    if not g0:
        return False
    if g0:
        if 'id' not in v:
            return False
        if 'name' not in v:
            return False
        if 'email' not in v:
            return False
        if 'tags' not in v:
            return False
    return True

def validate(v):
    try:
        return u0(v, 0, ())
    except RecursionError:
        raise MaxDepthExceededError("compiled evaluation exceeded the interpreter's stack; reduce nesting or lower max_depth") from None
