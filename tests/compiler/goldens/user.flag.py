def validate(v):
    try:
        return H_FRAG(T[0], v, (), 0)
    except RecursionError:
        raise MaxDepthExceededError("compiled evaluation exceeded the interpreter's stack; reduce nesting or lower max_depth") from None
