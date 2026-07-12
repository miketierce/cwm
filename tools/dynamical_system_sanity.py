#!/usr/bin/env python3
"""
Software sanity check for dynamical system tasks (PR #1 + PR #2 tasks 8-9).

Part A: Pure software — can random nonlinear kernels (no physics) reconstruct
        Lorenz, Mackey-Glass, and NARMA-10? Sets the bar for what CWM needs
        to beat.

Part B: Replay d3 physical reservoir readouts on the NARMA task they were
        captured for. Compare against software baselines computed from the
        same NARMA input sequence.

Usage: python3 tools/dynamical_system_sanity.py
"""
import numpy as np, json, time
from pathlib import Path
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import TimeSeriesSplit

results = {}
t0 = time.time()


def nmse(y_true, y_pred):
    v = np.var(y_true)
    return float(np.mean((y_true - y_pred) ** 2) / v) if v > 0 else float('inf')


def nrmse(y_true, y_pred):
    return float(np.sqrt(nmse(y_true, y_pred)))


def best_ridge(X_tr, y_tr, X_te, y_te):
    """Ridge with time-series CV to pick alpha."""
    sc = StandardScaler(); Xs = sc.fit_transform(X_tr); Xt = sc.transform(X_te)
    best_a, best_s = 1.0, float('inf')
    for a in [0.001, 0.01, 0.1, 1, 10, 100, 1000]:
        scores = []
        for tr, va in TimeSeriesSplit(n_splits=3).split(Xs):
            r = Ridge(alpha=a).fit(Xs[tr], y_tr[tr])
            scores.append(nmse(y_tr[va], r.predict(Xs[va])))
        m = np.mean(scores)
        if m < best_s:
            best_s, best_a = m, a
    r = Ridge(alpha=best_a).fit(Xs, y_tr)
    return nrmse(y_te, r.predict(Xt)), best_a


# ==============================================================
# Generate dynamical system data
# ==============================================================

def generate_narma10(n, seed=0):
    rng = np.random.default_rng(seed)
    u = rng.uniform(0, 0.5, n + 200)
    y = np.zeros(n + 200)
    for t in range(10, n + 200):
        y[t] = (0.3 * y[t-1] + 0.05 * y[t-1] * sum(y[t-1-i] for i in range(10))
                + 1.5 * u[t-1] * u[t-10] + 0.1)
    return u[200:], y[200:]


def generate_lorenz(n, dt=0.01, seed=0):
    rng = np.random.default_rng(seed)
    sigma, rho, beta = 10.0, 28.0, 8.0/3.0
    x, y, z = 1.0 + rng.normal(0, 0.01), 1.0, 1.0
    xs, ys, zs = [], [], []
    for _ in range(n + 5000):  # burn-in
        dx = sigma * (y - x) * dt
        dy = (x * (rho - z) - y) * dt
        dz = (x * y - beta * z) * dt
        x += dx; y += dy; z += dz
        xs.append(x); ys.append(y); zs.append(z)
    return np.array(xs[5000:]), np.array(ys[5000:]), np.array(zs[5000:])


def generate_mackey_glass(n, tau=17, seed=0):
    rng = np.random.default_rng(seed)
    history = 0.9 + rng.normal(0, 0.01, tau + 1)
    x = list(history)
    for t in range(tau, n + 5000 + tau):
        xt = x[t]
        xt_tau = x[t - tau]
        dx = 0.2 * xt_tau / (1 + xt_tau**10) - 0.1 * xt
        x.append(xt + dx)
    return np.array(x[5000 + tau:5000 + tau + n])


def make_delay_embedding(series, lag, dim):
    """Build delay-embedded input matrix."""
    n = len(series) - (dim - 1) * lag
    X = np.zeros((n, dim))
    for d in range(dim):
        X[:, d] = series[d * lag:d * lag + n]
    return X


def make_random_features(X_in, n_feat, rng, kind='relu'):
    d = X_in.shape[1]
    W = rng.normal(0, 1.0 / np.sqrt(d), (d, n_feat))
    b = rng.normal(0, 0.1, n_feat)
    if kind == 'relu':
        return np.maximum(0, X_in @ W + b)
    elif kind == 'tanh':
        return np.tanh(X_in @ W + b)
    elif kind == 'rff':
        return np.sqrt(2.0 / n_feat) * np.cos(X_in @ W + rng.uniform(0, 2*np.pi, n_feat))
    return X_in @ W + b


# ==============================================================
# PART A: Software-only baselines
# ==============================================================
print("=" * 65)
print("PART A: SOFTWARE BASELINES — random kernels on dynamical systems")
print("=" * 65)

N = 2000
rng = np.random.default_rng(42)
n_train = int(N * 0.7)

tasks = {}

# NARMA-10
u_narma, y_narma = generate_narma10(N + 10)
X_narma = make_delay_embedding(u_narma, lag=1, dim=10)
y_narma_target = y_narma[9:][:len(X_narma)]
tasks['NARMA-10'] = (X_narma, y_narma_target)

# Lorenz (predict x(t+1) from delay embedding of x)
lx, ly, lz = generate_lorenz(N + 50)
X_lorenz = make_delay_embedding(lx, lag=1, dim=10)
y_lorenz_target = lx[10:][:len(X_lorenz)]
tasks['Lorenz_x'] = (X_lorenz, y_lorenz_target)

# Lorenz cross-variable (predict z from x embedding)
y_lorenz_z = lz[10:][:len(X_lorenz)]
tasks['Lorenz_x->z'] = (X_lorenz, y_lorenz_z)

# Mackey-Glass (predict τ steps ahead)
mg = generate_mackey_glass(N + 50)
X_mg = make_delay_embedding(mg, lag=1, dim=10)
y_mg_target = mg[10:][:len(X_mg)]
tasks['Mackey-Glass'] = (X_mg, y_mg_target)

feature_sets = ['linear', 'quadratic', 'relu_100', 'relu_500',
                'tanh_100', 'tanh_500', 'rff_100', 'rff_500']

partA = {}
for tname, (X_in, y_target) in tasks.items():
    X_in = X_in[:N]; y_target = y_target[:N]
    print(f"\n  Task: {tname} ({len(y_target)} samples)")
    print(f"  {'Features':<20s} {'NRMSE':>8s} {'Dim':>6s}")
    print(f"  {'-'*20} {'-'*8} {'-'*6}")

    task_res = {}
    for fname in feature_sets:
        if fname == 'linear':
            Xf = X_in
        elif fname == 'quadratic':
            pairs = []
            for i in range(X_in.shape[1]):
                for j in range(i, X_in.shape[1]):
                    pairs.append(X_in[:, i] * X_in[:, j])
            Xf = np.column_stack([X_in] + pairs)
        else:
            kind, n_feat = fname.rsplit('_', 1)
            Xf = make_random_features(X_in, int(n_feat), rng, kind=kind)

        score, alpha = best_ridge(Xf[:n_train], y_target[:n_train],
                                  Xf[n_train:], y_target[n_train:])
        task_res[fname] = {'nrmse': round(score, 4), 'dim': Xf.shape[1]}
        print(f"  {fname:<20s} {score:>8.4f} {Xf.shape[1]:>6d}")

    partA[tname] = task_res

results['partA_software_baselines'] = partA
print(f"\n  [{time.time() - t0:.0f}s elapsed]")


# ==============================================================
# PART B: Replay d3 physical reservoir readouts
# ==============================================================
print("\n" + "=" * 65)
print("PART B: REPLAY d3 PHYSICAL RESERVOIR READOUTS")
print("=" * 65)

reservoir_files = sorted(Path('data/results/reservoir').glob('d3*readouts*.npz'))
partB = {}

for rf in reservoir_files:
    rd = np.load(rf)
    readouts = rd['readouts']  # (300, 27, 4)
    u = rd['u_narma']
    y = rd['y_narma']

    # Flatten readouts: (300, 108)
    X_phys = readouts.reshape(readouts.shape[0], -1)
    n = len(y)
    n_tr = int(n * 0.7)

    print(f"\n  File: {rf.name}")
    print(f"  Readouts: {readouts.shape} -> flat {X_phys.shape}")
    print(f"  NARMA samples: {n} ({n_tr} train / {n - n_tr} test)")

    # Build matching software features from same input u
    X_delay = make_delay_embedding(u, lag=1, dim=min(10, n))
    n_usable = min(len(X_delay), n)
    X_delay = X_delay[:n_usable]
    X_phys_use = X_phys[:n_usable]
    y_use = y[:n_usable]
    n_tr = int(n_usable * 0.7)

    file_res = {}
    candidates = {
        'PHYSICAL_readouts': X_phys_use,
        'linear_delay10': X_delay,
        'relu_108_delay': make_random_features(X_delay, 108, rng, 'relu'),
        'tanh_108_delay': make_random_features(X_delay, 108, rng, 'tanh'),
        'rff_108_delay': make_random_features(X_delay, 108, rng, 'rff'),
        'relu_500_delay': make_random_features(X_delay, 500, rng, 'relu'),
    }

    # Also combine physical + delay
    candidates['PHYSICAL+delay'] = np.column_stack([X_phys_use, X_delay])

    print(f"  {'Features':<25s} {'NRMSE':>8s} {'Dim':>6s}")
    print(f"  {'-'*25} {'-'*8} {'-'*6}")

    for fname, Xf in candidates.items():
        score, alpha = best_ridge(Xf[:n_tr], y_use[:n_tr],
                                  Xf[n_tr:], y_use[n_tr:])
        tag = " <-- PLATE" if "PHYSICAL" in fname else ""
        file_res[fname] = {'nrmse': round(score, 4), 'dim': Xf.shape[1]}
        print(f"  {fname:<25s} {score:>8.4f} {Xf.shape[1]:>6d}{tag}")

    partB[rf.name] = file_res

results['partB_physical_reservoir'] = partB

# ==============================================================
# Save
# ==============================================================
out = Path('data/results/dynamical_system_sanity.json')
json.dump(results, open(out, 'w'), indent=1)
print(f"\n{'=' * 65}")
print(f"Saved to {out}")
print(f"Total time: {time.time() - t0:.0f}s")
