# CWM DOOM Demo — First-Person Maze on a Glass Computer

**Date:** 2026-06-20
**Status:** Demo specification. Builds on the Phase 4A (HD compute / gradient kernel) infrastructure from [DESK_DEMONSTRATOR_PROTOCOL.md](DESK_DEMONSTRATOR_PROTOCOL.md).
**Prerequisites:** Phases 0–4A of the desk demonstrator (crossbar + census + CAM + gradient mode working).

**The headline:**

> A first-person maze running at 66–125 fps on a glass computer. The renderer is wave interference. The level data is permanently stored in the plates' eigenmode spectra. No RAM, no ROM, no CPU — just glass, a microphone, and a speaker.

**Two build paths:**

- **Stacked scrappy ($0):** 8 plates on 1 relay port, multi-tone + FFT readout, 37-dim kernel, 66 fps. Uses existing bench hardware. Needs multi-tone IMD validation.
- **32-plate FDM ($68):** 32 plates, frequency-division one-shot capture, 32-dim kernel, 125 fps. Needs new cassette build + FDM tuning.

---

## ⚠️ Wave-Native Warning (DOOM is the canonical silicon-trap)

**DOOM was attempted on the bench (2026-06-21) the silicon way and FAILED — and the failure is the lesson.** Hard raycasting renders by branching on the first wall-hit (discontinuous); a smooth analog kernel + ridge readout cannot represent a discontinuity (8 raycast columns scored R²≈0.00 on real glass). Do NOT build the renderer as a learned regression from state → hard column heights.

The wave-native paths, in order of proven-ness:

1. **Volumetric (fog) render** — integrate soft wall-occupancy along each ray (the NeRF trick). SMOOTH → learnable. Confirmed: per-column R² 0→+0.30, beats baseline.
2. **Factored associative recall** — don't resolve 1-of-512 jointly; resolve x, y, angle each by **nearest-centroid** (the T3.4 method), then look up the precomputed frame. The current bench resolves only ~2 levels/axis with **frequency-position** encoding; the proven 8-levels/axis needs **amplitude-of-fixed-mode** encoding (AWG/DAC drive), not the Pico NCO's fixed-amplitude frequency drive.
3. **Reduce the state space** to the measured resolution (e.g. 4×4×4) so each state is distinct.

**Do not claim DOOM renders on the present bench.** See the lab diary 2026-06-20 "DOOM Reframe" and [tools/cam_analysis.py](../tools/cam_analysis.py) / [tools/cam_recall.py](../tools/cam_recall.py).

---

## 1. What This Demo Proves

| Claim                           | Mechanism                                                         | Architecture section            |
| ------------------------------- | ----------------------------------------------------------------- | ------------------------------- |
| General compute on glass        | Raycasting = kernel evaluation + threshold per column             | §7A (discrete) + §7B (gradient) |
| The array IS the program        | Level geometry is encoded in which plates exist and their spectra | §7A.1                           |
| Permanent storage without write | The maze never needs to be "loaded" — it's in the glass forever   | §7A.4                           |
| Real-time inference             | 125 fps from physical kernel evaluation                           | §7B.3                           |
| Interpolation / generalization  | Smooth movement between grid positions via gradient weighting     | §7B.3 (interpolation primitive) |
| Zero-power game state           | Turn it off, turn it on — the level is still there                | §7A.4 (permanent tier)          |

**What it ISN'T:** a competitive game console. It's a 32-pixel-wide wireframe maze at desk clock speed. The point is not graphical fidelity — it's that wave interference is doing the computation.

---

## 2. System Specification

### 2.1 The maze

- **Grid:** 8×8 cells (64 squares, walls on edges)
- **Player state:** (x, y, angle) where x ∈ {0..7}, y ∈ {0..7}, angle ∈ {0..7} (8 directions, 45° steps)
- **Total render states:** 8 × 8 × 8 = 512 possible views
- **Display:** 8 columns, each showing a wall-distance value (mapped to column height)

### 2.2 The plate array (32 plates)

Each plate encodes one "view cluster" — a region of the state space. With 32 plates and 512 possible views:

- Each plate covers ~16 nearby views
- The kernel gradient interpolates between plates for smooth transitions
- Plates are chosen to sample the state space at maximally informative positions (corners, corridor junctions, dead ends)

**Plate encoding:** each plate's eigenmode spectrum is its natural state — NOT modified. Instead, the **mapping from view → plate** is discovered during the census:

1. Census all 32 plates (Phase 0)
2. Assign each plate to a "view" based on its spectral signature
3. Build the kernel matrix K (32×32)
4. Train the readout weights to map gradient → 8 column heights

### 2.3 Display

- **8-column LED bar graph** (or 8-pixel OLED column) — each column height = wall distance for that screen column
- Alternatively: the **onboard web UI** renders the first-person view + overhead map in the browser
- Both can run simultaneously

### 2.4 Input

- USB gamepad / keyboard: W (forward), A (turn left), S (back), D (turn right)
- Maps to state transitions: W → advance one cell in facing direction (if no wall), A/D → rotate angle ±1 step

---

## 3. Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  PLAYER INPUT (gamepad / keyboard / web UI)                         │
│  W/A/S/D → state register: (x, y, angle)                           │
└─────────────────────┬───────────────────────────────────────────────┘
                      │ state → query vector
                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│  QUERY ENCODER (FPGA / host)                                        │
│  (x, y, angle) → multi-tone drive waveform                         │
│  Encodes player state as a spectral "question" to the array        │
└─────────────────────┬───────────────────────────────────────────────┘
                      │ drive waveform
                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│  PLATE ARRAY (32 plates, crossbar-addressed)                        │
│  ┌────┬────┬────┬────┬────┬────┬────┬────┐                         │
│  │ P1 │ P2 │ P3 │ P4 │ P5 │ P6 │ P7 │ P8 │  shelf 1              │
│  ├────┼────┼────┼────┼────┼────┼────┼────┤                         │
│  │ P9 │P10 │P11 │P12 │P13 │P14 │P15 │P16 │  shelf 2              │
│  ├────┼────┼────┼────┼────┼────┼────┼────┤                         │
│  │P17 │P18 │P19 │P20 │P21 │P22 │P23 │P24 │  shelf 3              │
│  ├────┼────┼────┼────┼────┼────┼────┼────┤                         │
│  │P25 │P26 │P27 │P28 │P29 │P30 │P31 │P32 │  shelf 4              │
│  └────┴────┴────┴────┴────┴────┴────┴────┘                         │
│  ALL plates respond to broadcast query simultaneously               │
│  → gradient response y = [y₁, y₂, ..., y₃₂]                       │
└─────────────────────┬───────────────────────────────────────────────┘
                      │ 32-element gradient vector
                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│  RENDER READOUT (FPGA: w · y → 8 column heights)                    │
│  8 trained weight vectors (one per display column)                  │
│  column_height[c] = w_c · y   for c = 0..7                         │
└─────────────────────┬───────────────────────────────────────────────┘
                      │ 8 column heights
                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│  DISPLAY                                                            │
│  8-column LED bar / web UI / OLED                                   │
│  Overhead map shows player position + direction                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.1 Render pipeline timing

| Step      | Operation                                                      | Time                                           |
| --------- | -------------------------------------------------------------- | ---------------------------------------------- |
| 1         | State → query encoding (host/FPGA)                             | ~10 µs                                         |
| 2         | Broadcast drive → all plates ring up                           | ~3 ms (at Q≈500, f≈50 kHz)                     |
| 3         | Capture gradient (32 plate responses via FDM or crossbar scan) | ~4 ms (FDM: one capture; crossbar: sequential) |
| 4         | Compute 8 column heights (8 dot products, 32 elements each)    | ~5 µs (FPGA)                                   |
| 5         | Update display                                                 | ~100 µs                                        |
| **Total** |                                                                | **~7–8 ms = 125–140 fps**                      |

With FDM (frequency-diversified cartridge + single-capture): **one acoustic cycle per frame.**
With serial crossbar scan (32 sequential reads): 32 × 4 ms = 128 ms per frame ≈ 8 fps (still playable for a maze walker, but FDM is the target).

### 3.2 Collision detection

Wall map = a 64-bit lookup table (8×8 grid, 4 walls per cell = 256 bits, compressed). Stored in FPGA memory (not in the glass). When the player presses W:

1. Compute target cell = current cell + facing direction
2. Check the wall bit for that edge
3. If no wall → update (x, y); if wall → no movement

This is 1 FPGA clock cycle. The glass doesn't do collision — it does rendering.

### 3.3 State encoding (the query compiler)

The player state (x, y, angle) must be encoded as a drive waveform that the array can distinguish. Three encoding options (choose during calibration):

**Option A — Frequency encoding:** x → mode cluster 1 amplitude, y → mode cluster 2 amplitude, angle → mode cluster 3 amplitude. Each axis gets a different frequency band.

**Option B — Multi-tone hash:** define 32 "basis queries" (one per plate), each a unique multi-tone signature. The player state selects a weighted combination of nearby basis queries. The kernel naturally interpolates.

**Option C — Learned encoding (best):** during training (step 7 below), learn the optimal query waveform for each state using gradient descent on render error. The encoder is a small lookup table: 512 states → 512 drive waveforms (each is M tone amplitudes/phases). Store in host memory.

---

## 4. The Maze Level

### 4.1 Level design (E1M1 of CWM-DOOM)

```
 ┌───┬───┬───┬───┬───┬───┬───┬───┐
 │   │                       │   │
 ├   ┼   ┼ ─ ┼   ┼ ─ ┼   ┼   ┼   │
 │       │       │           │   │
 ├   ┼ ─ ┼   ┼   ┼   ┼ ─ ┼   ┼   │
 │   │       │       │       │   │
 ├   ┼   ┼ ─ ┼ ─ ┼   ┼   ┼ ─ ┼   │
 │               │       │       │
 ├ ─ ┼   ┼   ┼   ┼ ─ ┼   ┼   ┼   │
 │       │       │       │       │
 ├   ┼ ─ ┼   ┼   ┼   ┼ ─ ┼ ─ ┼   │
 │   │       │           │       │
 ├   ┼   ┼ ─ ┼   ┼ ─ ┼   ┼   ┼   │
 │               │       │   │   │
 ├   ┼ ─ ┼ ─ ┼   ┼   ┼ ─ ┼   ┼   │
 │   │           │           │   │
 └───┴───┴───┴───┴───┴───┴───┴───┘

 Legend: ─ │ = wall segments;  spaces = open passages
 Start: (0,0) facing East
 Goal: (7,7) — mark with a distinct plate response
```

The maze is designed to have:

- One solution path (solvable)
- Several dead ends (tests smooth turning)
- A mix of long corridors and tight corners (tests interpolation)
- Visually distinct regions (different wall densities → different column-height patterns)

### 4.2 Ground-truth render

For every (x, y, angle) state, compute the TRUE column heights by software raycasting:

```python
def raycast(maze, x, y, angle, n_columns=8):
    """Return 8 wall distances for the given player state."""
    heights = []
    fov = 60  # degrees
    for col in range(n_columns):
        ray_angle = angle - fov/2 + col * fov / (n_columns - 1)
        dist = cast_single_ray(maze, x, y, ray_angle)
        heights.append(1.0 / max(dist, 0.1))  # perspective: closer = taller
    return heights
```

This produces the 512×8 target matrix T (512 views × 8 column heights). This is the training target for the glass renderer.

---

## 5. Build Steps (assumes Phases 0–4A complete)

### Step 1 — Expand the cartridge to 32 plates

**Objective:** Build and census a 32-plate diversified cartridge on the crossbar.

**Procedure:**

1. Source 32 glass slides (microscope slides or 25mm plates). Diversify them:
   - 8 × 4 thickness grades (0.8 / 0.9 / 1.0 / 1.1 mm), or
   - Same thickness + graded tuning masses (CA glue dots, stepped 1–8 mg)
2. Build a 4-shelf card cage (8 plates per shelf, nodal foam mounts, shared TX rail per shelf).
3. Wire all 32 to the crosspoint switch(es):
   - One MT8816 (8×16) handles 128 crosspoints → more than enough for 32 plates.
   - Or: two cascaded crosspoint ICs (DD21 × 2) for the full 4×8 shelf layout.
4. Run Phase 0 census on all 32 plates. Record mode maps.
5. Verify band separation: all 32 must be FDM-resolvable in a single capture. If collisions exist, re-tune until clean.

**Success:** 32 plates censused, FDM-separated, crossbar-addressable.
**Time:** 2 days (build) + 1 day (census).

### Step 2 — Build the 32×32 kernel matrix

**Objective:** Characterize the full inter-plate similarity structure.

**Procedure:**

1. For each plate $i$ (i = 1..32), define its "canonical query" = drive at its tag mode(s) at reference amplitude.
2. Broadcast each canonical query and capture ALL 32 plates' responses → row $i$ of the kernel matrix K.
3. Repeat for all 32 → complete K ∈ ℝ³²ˣ³².
4. SVD of K: report rank, condition number, eigenspectrum.
5. Visualize K as a heatmap. Confirm:
   - Diagonal-dominant (each plate matches itself best)
   - Rank ≥ 20 (need diversity for a 512-state interpolation task)
   - Off-diagonals show smooth gradient (nearby plates in the cage are somewhat correlated — this is useful for interpolation)

**Success:** K is rank ≥ 20, well-conditioned (κ < 100), diagonal-dominant.
**Kill:** rank < 10 ⇒ plates are too similar; diversify further.
**Time:** 1 session.

### Step 3 — Design the state → query encoding

**Objective:** Map the 512 player states to drive waveforms that the 32-plate kernel can resolve.

**Procedure:**

1. **Assign plate "views."** From the 512 states, pick 32 "anchor states" (uniformly spaced in the maze, covering all 8 directions). Assign each anchor to one plate.
2. **Define the anchor queries.** For anchor state $a_j$ (assigned to plate $j$), set the query = plate $j$'s canonical drive (the one that maximizes $y_j$).
3. **Interpolation for non-anchor states.** For an arbitrary state $s$:
   - Find the 3–4 nearest anchors (by Euclidean distance in (x, y, angle) space).
   - Blend their queries: $q(s) = \sum_{j \in \text{near}} w_j(s) \cdot q(a_j)$, where $w_j$ decreases with distance (inverse-distance weighting or RBF).
4. Store the 512 query waveforms in a lookup table on the host (512 × M_tones floats). At runtime, state → table lookup → drive.

**Alternative (learned encoder, better accuracy):** skip the manual assignment and learn the optimal query for each state during training (Step 7). This is a small optimization problem: find query waveforms that minimize render error after kernel + readout.

**Success:** 512 queries defined; spot-check 10 random states and confirm gradient responses show meaningful variation (not all identical).
**Time:** 1 session (scripted).

### Step 4 — Generate ground-truth renders

**Objective:** Compute the target column heights for all 512 states.

**Procedure:**

1. Define the maze as a data structure (8×8 grid, wall bits per edge).
2. For each of the 512 states (x, y, angle), run the software raycaster → 8 column heights (normalized 0–1, where 1 = wall right in front, 0 = maximum visibility distance).
3. Store as T ∈ ℝ⁵¹²ˣ⁸ (target matrix).
4. Visualize: for 8 sample states, plot the column heights as a bar graph → confirm they look like reasonable first-person wall patterns.

**Success:** T computed, visually sensible.
**Time:** 30 minutes (software only).

### Step 5 — Collect training data (physical kernel evaluation)

**Objective:** Broadcast all 512 queries through the physical array and capture the gradients.

**Procedure:**

1. For each of the 512 encoded queries (from Step 3):
   a. Broadcast the query waveform on the shared TX rail.
   b. Capture the 32-plate gradient response (FDM single-capture or crossbar sequential scan).
   c. Store as row $k$ of the response matrix Y ∈ ℝ⁵¹²ˣ³².
2. Total captures: 512. At ~8 ms per capture (FDM): ~4 seconds total. At ~128 ms per capture (serial crossbar): ~65 seconds.
3. Normalize Y: each column to zero mean, unit variance (standard kernel preprocessing).

**Success:** Y collected, rank(Y) ≥ 20, no NaN/inf.
**Time:** 1 session.

### Step 6 — Train the render readout

**Objective:** Learn 8 weight vectors (one per display column) that map the 32-dim gradient to column heights.

**Procedure:**

1. For each display column $c$ (c = 0..7):
   - Target: $\mathbf{t}_c$ = column $c$ of T (512 values).
   - Features: Y (512 × 32).
   - Solve: $\mathbf{w}_c = (\mathbf{Y}^T\mathbf{Y} + \lambda I)^{-1}\mathbf{Y}^T\mathbf{t}_c$ (ridge regression, λ = 0.01).
2. Store the 8 weight vectors: W ∈ ℝ⁸ˣ³² (8 readout vectors, 32 elements each = 256 floats total).
3. Evaluate training accuracy:
   - Predicted: $\hat{\mathbf{T}} = Y \cdot W^T$
   - RMSE per column: $\text{RMSE}_c = \sqrt{\text{mean}((\hat{T}_{:,c} - T_{:,c})^2)}$
   - Target: RMSE < 0.15 (on [0,1] scale) for all columns.
4. Visualize: pick 16 random states, plot predicted vs ground-truth column heights side by side.

**Success:** RMSE < 0.15 for all 8 columns; visual render looks recognizably correct (walls in the right places, heights proportional to distance).
**Kill:** RMSE > 0.3 for multiple columns ⇒ the kernel doesn't have enough diversity to resolve the maze states. Possible fixes: (a) add more plates, (b) improve query encoding, (c) reduce maze complexity to 4×4.
**Time:** 30 minutes (pure computation, scripted).

### Step 7 — (Optional) Refine query encoding via gradient descent

**Objective:** Improve render accuracy by optimizing the query waveforms.

**Procedure:**

1. Define loss: $L = \sum_{k,c} (\hat{T}_{k,c} - T_{k,c})^2$ where $\hat{T}_{k,c} = \mathbf{w}_c^T \mathbf{y}(q_k)$ and $\mathbf{y}(q_k)$ is the physical gradient response to query $q_k$.
2. For each query $q_k$: perturb each tone amplitude/phase by ±δ; measure the change in gradient → numerical Jacobian ∂y/∂q.
3. Gradient step: $q_k \leftarrow q_k - \eta \cdot \nabla_q L$ (using the chain rule through the physical kernel).
4. Repeat for ~5 passes over the 512 queries (5 × 512 = 2,560 additional measurements).
5. Retrain readout W on the improved Y.

**Note:** this is optional. If Step 6 accuracy is sufficient (RMSE < 0.15), skip this. It's the "fine-tuning" step — takes significant bench time for marginal improvement.

**Success:** RMSE drops below 0.10.
**Time:** 2–4 hours of automated measurement.

### Step 8 — Build the display

**Objective:** Real-time visual output for the rendered columns.

**Option A — LED bar graph (simplest, most visceral):**

1. Source an 8-column LED bar display (e.g., 8× LM3914 dot/bar driver + LED columns, or a pre-made 8×8 LED matrix).
2. Wire to 8 GPIO/PWM outputs from the Red Pitaya (or an Arduino driven by the host).
3. Map column_height (0–1) → LED count (0–8 LEDs lit in that column).
4. Update rate: as fast as the render pipeline runs (~125 fps with FDM).

**Option B — Web UI (richer, already in the desk rig):**

1. The existing web UI (§3.9 of the desk spec) serves a page with:
   - Canvas: 8-column first-person view (rectangles, height proportional to column_height, darker = farther)
   - Overhead map: 8×8 grid showing walls + player position/direction arrow
   - Stats: fps counter, current (x,y,angle), RMSE vs ground truth
2. WebSocket pushes column heights at render rate → browser draws at requestAnimationFrame (60 fps cap is fine).

**Option C — Both** (LED bar for the physical demo, web UI for the detailed view).

**BOM addition:**

| #    | Item                                     | For                  | Qty | Est. | Source                                                                               |
| ---- | ---------------------------------------- | -------------------- | --- | ---- | ------------------------------------------------------------------------------------ |
| DD28 | 8×8 LED matrix + MAX7219 driver          | first-person display | 1   | ~$5  | search ["8x8 LED matrix MAX7219"](https://www.amazon.com/s?k=8x8+LED+matrix+MAX7219) |
| DD29 | USB gamepad (or keyboard — already have) | player input         | 1   | ~$10 | on hand / any USB gamepad                                                            |

**Success:** display updates in sync with render pipeline; column heights visually correspond to the player's view direction.
**Time:** 1 session.

### Step 9 — Wire the game loop

**Objective:** Close the loop: input → state → query → kernel → readout → display.

**Procedure:**

1. Write `tools/cwm_desk/doom.py` (or add to the orchestrator):

```python
class CWMDoom:
    def __init__(self, maze, query_table, readout_W, kernel_interface):
        self.maze = maze           # 8×8 wall map
        self.queries = query_table # 512 × M_tones
        self.W = readout_W         # 8 × 32
        self.kernel = kernel_interface  # broadcasts, captures gradient
        self.state = (0, 0, 0)     # (x, y, angle) — start position

    def render_frame(self):
        """One frame: state → query → kernel → column heights."""
        idx = self.state_to_index(*self.state)
        query = self.queries[idx]
        gradient = self.kernel.broadcast_and_capture(query)  # 32 floats
        columns = self.W @ gradient                          # 8 floats
        return columns

    def handle_input(self, key):
        """W/A/S/D → update state (with collision check)."""
        x, y, angle = self.state
        if key == 'A':
            angle = (angle - 1) % 8
        elif key == 'D':
            angle = (angle + 1) % 8
        elif key == 'W':
            dx, dy = DIRECTION_VECTORS[angle]
            nx, ny = x + dx, y + dy
            if self.maze.passable(x, y, angle):
                x, y = nx, ny
        elif key == 'S':
            dx, dy = DIRECTION_VECTORS[(angle + 4) % 8]
            nx, ny = x + dx, y + dy
            if self.maze.passable(x, y, (angle + 4) % 8):
                x, y = nx, ny
        self.state = (x, y, angle)

    def run(self):
        """Main loop."""
        while True:
            columns = self.render_frame()
            self.display.update(columns)
            key = self.input.poll()
            if key:
                self.handle_input(key)
```

2. Plug in the kernel interface:
   - **FDM path:** broadcast query → one capture → FFT → extract 32 plate amplitudes.
   - **Crossbar serial path:** for each plate, select via crosspoint → capture → amplitude. Slower but works without FDM.
3. Plug in display (LED matrix via GPIO, or WebSocket to browser).
4. Run the loop. Confirm: pressing W moves forward (view changes), A/D rotates (columns shift left/right), walls appear at correct positions.

**Success:** playable maze — player can navigate from (0,0) to (7,7) using the rendered view.
**Time:** 1 session.

### Step 10 — Validate render accuracy in real-time

**Objective:** Confirm the glass renderer matches the software raycaster during gameplay.

**Procedure:**

1. Run both renderers in parallel: glass (physical kernel) and software (ground truth).
2. Display both side by side in the web UI.
3. Walk the entire maze. For each frame, compute:
   - Per-column absolute error: |glass_height - truth_height|
   - Frame RMSE
4. Record statistics:
   - Mean frame RMSE across all visited states
   - Worst-case frame (max RMSE)
   - Percentage of frames where all 8 columns are within ±1 LED unit of truth

**Success criteria:**

- Mean RMSE < 0.15
- ≥ 80% of frames within ±1 LED unit on all columns
- Player can solve the maze using ONLY the glass-rendered view (no overhead map)

**Kill:** glass render is too inaccurate to navigate (player gets lost in open areas) ⇒ either add plates (48 or 64) or reduce maze to 6×6.
**Time:** 1 session.

### Step 11 — Polish and demo mode

**Objective:** Make it presentable.

**Procedure:**

1. **Title screen:** LED matrix shows "CWM" scrolling, or web UI shows title card.
2. **Auto-play mode:** pre-recorded solution path plays automatically (for booth/video mode).
3. **Metrics overlay:** fps counter, "kernel evals: N", "plates: 32", "no CPU in the render path."
4. **Victory condition:** reaching (7,7) triggers a distinct plate response (plate 32's tag mode, full amplitude) → LED matrix flashes / web UI shows "LEVEL COMPLETE."
5. **One-button start:** the physical run button (DD27) starts the game.
6. **Video capture:** record a gameplay session (screen capture + overhead of the rig) for the project YouTube/social.

**The demo script (for a funder/journalist):**

> "This is a first-person maze game. The display shows 8 columns — wall heights, like Wolfenstein 3D. I press forward and the view changes in real time."
>
> "What's computing the view? Not a CPU. Not a GPU. Not software. Those 32 glass plates in the rack — their natural vibration patterns ARE the level data. When I move, a sound wave asks them 'what should I see from here?' and all 32 plates answer simultaneously. The loudness of each plate's response tells me how close the walls are. Wave interference IS the renderer."
>
> "The level was never loaded. There's no RAM, no ROM. The maze exists because those specific plates exist. Swap the plates, swap the level. Turn off the power, turn it back on — the level is still there. It's stored in the geometry of the glass."
>
> "Right now it's 32 plates and 125 frames per second. On a MEMS chip with 10,000 cells, it's the same architecture at 3,000 fps."

---

## 6. Performance Projections

| Configuration                            | Plates | Ports | Readout mode                | Kernel dim   | Frames/sec | Notes                                    |
| ---------------------------------------- | ------ | ----- | --------------------------- | ------------ | ---------- | ---------------------------------------- |
| **Desk (serial crossbar, 1:1)**          | 32     | 32    | single-tone sequential scan | 32           | ~8         | Original spec — works but slow           |
| **Desk (FDM capture, 1:1)**              | 32     | 32    | FDM one-shot                | 32           | ~125       | Gold standard — requires FDM hardware    |
| **Stacked scrappy (8 plates, 1 port)**   | 8      | 1     | multi-tone + single FFT     | ~37          | **~66**    | Zero relay switching — existing hardware |
| **Stacked scrappy (16 plates, 2 ports)** | 16     | 2     | multi-tone + single FFT     | ~67 per port | **~33**    | Only 1 relay switch per frame            |
| **Stacked + Red Pitaya**                 | 8      | 1     | multi-tone + lock-in        | ~37          | ~200       | If Red Pitaya does parallel demod        |
| **MEMS (10⁴ cells)**                     | 10,000 | —     | Integrated                  | 10,000       | ~3,000     | Full resolution, real-time               |

### 6.1 Stacked scrappy path (achievable NOW on existing relay hardware)

The "32-plate FDM" path is the luxury option. **Spectral port multiplexing** (see [DESK_DEMONSTRATOR_SCRAPPY.md §8.4](DESK_DEMONSTRATOR_SCRAPPY.md)) provides an alternative:

**Principle:** Wire multiple plates to one relay port. Drive all their resonances simultaneously as a multi-tone burst. Capture one FFT — extract amplitude at each mode's frequency bin. One port, one capture, k features.

**Why it works:** Q ≈ 200 gives 40–60 dB isolation between modes separated by > f/Q (~500 Hz). The FFT separates them the way FDM would — except the "channels" are frequency bins on one physical wire, not separate wires.

**Concrete configuration for DOOM:**

- 8 plates (existing cassette), all wired to 1 relay port
- Multi-tone drive: all ~37 usable modes excited simultaneously
- Single FFT capture: PicoScope block mode, 10 ms window → 100 Hz bin resolution
- Extract 37 amplitudes → 37-dim kernel
- Ridge regression → 8 column heights (same training as §5 Step 6)
- **Frame time:** 10 ms capture + 5 ms processing = **15 ms → 66 fps**
- **No relay switching during gameplay.** Zero. The relay just selects the port at startup.

**What changes from the 32-plate spec:**

| Aspect             | 32-plate FDM             | 8-plate stacked (1 port)  |
| ------------------ | ------------------------ | ------------------------- |
| Plates needed      | 32 (build new cassette)  | 8 (existing)              |
| Capture hardware   | FDM-capable ADC          | PicoScope (existing)      |
| Kernel dimension   | 32                       | 37 (more!)                |
| Frame rate         | 125 fps                  | 66 fps (sufficient)       |
| New parts cost     | ~$68                     | **$0**                    |
| Build time         | 2–3 days                 | 1 hour (re-wire + census) |
| Spectral diversity | 32 different plates      | 8 plates × multi-mode     |
| Risk               | Tuning 32 plates for FDM | IMD from multi-tone drive |

**Prerequisite validation (before committing to this path):**

1. Wire 2+ plates to one port
2. Drive multi-tone burst (all known modes simultaneously)
3. Capture FFT — confirm all peaks resolve at expected amplitude (no IMD contamination)
4. If pass → the stacked DOOM path is go. If fail → fall back to 32-plate FDM.

The 32-plate FDM path remains valid (and gives 125 fps + more spectral diversity), but **DOOM is playable today on existing hardware if multi-tone readout validates.**

---

## 7. Bill of Materials

### 7.1 Stacked scrappy path ($0 new — existing hardware)

| #    | Item                              | Status                           |
| ---- | --------------------------------- | -------------------------------- |
| —    | 8-plate cassette (3 RX PZTs each) | Owned                            |
| —    | 16-relay + 8-relay boards         | Owned                            |
| —    | PicoScope 2204A (FFT capture)     | Owned                            |
| —    | Pico NCO (multi-tone drive)       | Owned                            |
| —    | Preamp boards A/D                 | Owned                            |
| DD28 | 8×8 LED matrix + MAX7219 driver   | ~$5 (optional — web UI suffices) |

**Total new cost (stacked path): $0–$5.**

### 7.2 32-plate FDM path (luxury — $68 beyond Phase 4A)

| #    | Item                                              | For                  | Qty     | Est. | Source                                                                               |
| ---- | ------------------------------------------------- | -------------------- | ------- | ---- | ------------------------------------------------------------------------------------ |
| DD28 | 8×8 LED matrix + MAX7219 driver                   | first-person display | 1       | ~$5  | search ["8x8 LED matrix MAX7219"](https://www.amazon.com/s?k=8x8+LED+matrix+MAX7219) |
| DD29 | USB gamepad (generic)                             | player input         | 1       | ~$10 | any USB gamepad / keyboard on hand                                                   |
| —    | 24 additional glass slides (expand from 8 to 32)  | plate array          | 24      | ~$3  | same source as DD6                                                                   |
| —    | Additional tuning masses / PZTs for 24 new plates | diversify + drive    | 24 sets | ~$30 | DD7 + CA glue                                                                        |
| —    | Larger card cage (4 shelves × 8 slots)            | housing              | 1       | ~$20 | laser-cut acrylic / 3D print                                                         |

**Total new cost (FDM path):** ~$68 beyond the existing Phase 4A rig.

---

## 8. What Could Go Wrong

| Risk                                                        | Path affected   | Likelihood                                                           | Mitigation                                                                                        |
| ----------------------------------------------------------- | --------------- | -------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| Multi-tone IMD contaminates adjacent bins                   | Stacked         | Medium                                                               | Validate with 2-plate test first; reduce drive amplitude; skip contaminated bins                  |
| 8 plates provide insufficient spectral diversity (rank < 6) | Stacked         | Low–Medium                                                           | 8 plates × 5 modes = 40 raw; need rank ≥ 8 of 37. Likely OK but census will tell                  |
| Capacitive loading degrades preamp (8 PZTs in parallel)     | Stacked         | Low                                                                  | ~12 nF total; preamp BW > 200 kHz still. Add buffer op-amp if not (~$2)                           |
| 32 plates not spectrally diverse enough (K rank < 15)       | FDM             | Medium                                                               | Diversify more aggressively (thicker/thinner, larger tuning masses); worst case: drop to 6×6 maze |
| FDM collisions (two plates in same band)                    | FDM             | Medium                                                               | Budget time for iterative re-tuning; accept a few serial-readout plates if needed                 |
| Render RMSE too high for navigation                         | Both            | Medium                                                               | Reduce maze complexity (fewer walls, wider corridors); add plates; use Option C encoder           |
| Game is too slow                                            | FDM-serial only | Low                                                                  | Stacked path gives 66 fps; FDM gives 125 fps; only serial crossbar (8 fps) is borderline          |
| Interpolation fails at corridor junctions                   | Medium          | Add anchor plates specifically at junctions; use local RBF weighting |

---

## 9. Scaling: from 8×8 to DOOM

The architecture is the same at every scale — only the array size and readout strategy change:

| Maze                     | Resolution  | Plates needed | Readout mode              | Kernel dim | FPS (desk) | FPS (MEMS) |
| ------------------------ | ----------- | ------------- | ------------------------- | ---------- | ---------- | ---------- |
| **4×4 (proof)**          | 4 columns   | 4             | Stacked (1 port)          | ~19        | ~66        | 5,000      |
| **8×8 (this demo)**      | 8 columns   | 8             | Stacked (1 port)          | ~37        | ~66        | 3,000      |
| **8×8 (FDM luxury)**     | 8 columns   | 32            | FDM one-shot              | 32         | ~125       | 3,000      |
| **16×16**                | 16 columns  | 16 (2 ports)  | Stacked (2 ports)         | ~67        | ~33        | 3,000      |
| **32×32 (Wolf3D-scale)** | 32 columns  | 48 (4 ports)  | Stacked (4 ports)         | ~120       | ~16        | ~1,000     |
| **DOOM E1M1**            | 320 columns | ~200+         | MEMS or massively stacked | 1,000+     | —          | ~100       |

**The stacked scrappy insight:** the 8×8 demo (the one that matters for desk proof) is achievable at 66 fps on existing hardware. You don't need to scale to 32 plates first. The FDM 32-plate path is the upgrade for smoother performance and higher fidelity, not the prerequisite.

At MEMS scale, the 10⁴-cell array is a dedicated "render engine in glass" — running a full Wolfenstein-class raycaster at >1,000 fps with nJ per frame. Not competitive with a GPU, but competitive with **ultra-low-power edge vision processors** (the kind in VR headsets, robotics, always-on spatial awareness).

---

## 10. Cross-References

- Desk demonstrator build spec: [DESK_DEMONSTRATOR.md](DESK_DEMONSTRATOR.md)
- Phase 4A protocol (Parts A–D, prerequisite): [DESK_DEMONSTRATOR_PROTOCOL.md](DESK_DEMONSTRATOR_PROTOCOL.md)
- Architecture §7A (associative/HD compute): [CWM_PHONONIC_PROCESSOR_ARCHITECTURE.md](CWM_PHONONIC_PROCESSOR_ARCHITECTURE.md) §7A
- Architecture §7B (gradient/kernel compute): [CWM_PHONONIC_PROCESSOR_ARCHITECTURE.md](CWM_PHONONIC_PROCESSOR_ARCHITECTURE.md) §7B
- Spectral port multiplexing (stacking theory + validation): [DESK_DEMONSTRATOR_SCRAPPY.md](DESK_DEMONSTRATOR_SCRAPPY.md) §8.4
- Crossbar array (the addressing layer): [DESK_DEMONSTRATOR.md](DESK_DEMONSTRATOR.md) §3.2
- FDM readout (the speed key): [DESK_DEMONSTRATOR_PROTOCOL.md](DESK_DEMONSTRATOR_PROTOCOL.md) Phase 3
- Control interface / orchestrator: [DESK_DEMONSTRATOR.md](DESK_DEMONSTRATOR.md) §3.9
