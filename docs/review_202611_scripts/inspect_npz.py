import sys, numpy as np, json
for p in sys.argv[1:]:
    print("=====", p)
    d = np.load(p, allow_pickle=True)
    for k in d.files:
        a = d[k]
        try:
            print(f"  {k:28s} shape={a.shape} dtype={a.dtype}", end="")
            if a.dtype == object or a.ndim == 0:
                s = str(a.item() if a.ndim == 0 else a)[:600]
                print("  ::", s)
            else:
                print()
        except Exception as e:
            print("  err", e)
