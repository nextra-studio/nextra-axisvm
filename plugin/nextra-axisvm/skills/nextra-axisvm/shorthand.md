---
description: edit {ops} grammar: one action per line for geometry, sections, supports, loads, combinations
---
# NextraAxisVM shorthand (`edit {ops:'…'}`)

One action per line. Lines apply independently, and a failed line is reported with its reason while the others stay applied (`atomic:true` = all or nothing). `#` starts a comment. The whole call is one AxisVM undo step.

**Units:** coordinates and thickness in **m** (change with `units mm`), forces in **kN**, line loads in **kN/m**, area loads in **kN/m²**, moments in **kNm**.
**Points:** `x,y,z` (an existing node within the tolerance of 1 mm is reused) or a node handle `n5`.
**Names with spaces** are fine after `key=`: `sec=IPE 300 mat=S 235`. A value runs until the next `key=`.

## Settings
```
units mm                 # coordinates/thickness in mm from here on (m | cm | mm)
tol 0.002                # node merge tolerance (current units)
use mat=S 235 sec=IPE 300 t=0.25     # defaults for the following lines
mat S = S 235            # alias (catalog name; the model's design code first, then Eurocode)
sec C = HEB 240          # alias: catalog profile …
sec R = rect 300x500     # … or parametric, in mm: rect BxH · rhs BxHxT · shs BxT · pipe DxT · circle D
```

## Members
```
beam   0,0,3.5 6,0,3.5 sec=IPE 300 mat=S 235        # beam element
column 0,0,0 0,0,3.5 sec=HEB 240                    # = beam (vertical)
rib    …   truss …   line …                         # rib (on slab edges), truss (axial only), plain line (no element)
beam   0,0,3.5 6,0,3.5 12,0,3.5                     # polyline: one line per segment
beam   l3 l4 sec=IPE 330                            # define existing lines
column 0,0,0 0,0,3.5 sec=HEB 240 @ x=0:6:24 y=0,6   # repeat with offsets: x/y/z lists "0,6" or ranges start:step:end
beam   0,0,3.5 6,0,3.5 start=hinge end=hinge        # end releases at creation (hinge = My,Mz free)
```
Segments are **split at existing nodes** on them, and existing lines are split at new nodes, so members connect (`split=no` disables the first). A beam whose line becomes a slab edge is converted to a **rib** by AxisVM.

## Surfaces
```
slab  0,0,3.5 12,0,3.5 12,6,3.5 0,6,3.5 t=0.25 mat=C30/37     # plate (bending); edges reuse beam lines
plate … · shell … · wall … (= shell) · membrane …
shell l1 l2 l3 l4 t=0.2 mat=C30/37                            # from existing contour lines
slab  0,0,3.5 6,0,3.5 6,6,3.5 0,6,3.5 t=0.2 @ x=0,6,12          # repeat
hole  d1 2,2,3.5 3,2,3.5 3,3,3.5 2,3,3.5                        # opening in domain d1
```

## Supports and releases
```
support n1 n4 fixed            # fixed | pinned | roller (z only) | xyz | xyzrz (axes, rz… rotations) | k=kx,ky,kz,kxx,kyy,kzz
support z=0 fixed              # every node in the plane z=0 (also x=…, y=…)
support 0,0,0 12,0,0 pinned    # at points (a node is created if missing)
support l3 pinned              # line support (global)
release l9 l10 both=hinge      # or start=hinge / end=hinge / start=free:yy,zz / rigid
```

## Load cases, loads, combinations
```
case G self                    # create case G and add self-weight of all members and domains
case Q
load Q d1 d2 pz=-3             # area load on domains [kN/m²] (global; 'local', 'projected' allowed)
load G l7 l8 qz=-2             # uniform line load on the full length of beams/ribs [kN/m] (qx qy qz)
load S l7 projected qz=-1.5    # per m of plan length (snow on a rafter); 'local' = member axes
load Q n5 fz=-10 mx=2          # nodal force/moment [kN, kNm]: fx fy fz mx my mz
load Q 6,0,3.5 fz=-10          # at a point
load G self                    # self-weight into an existing case
combo ULS = 1.35 G + 1.5 Q     # type from the name (uls/sls) or explicit: combo C1 quasi = 1 G + 0.3 Q
```
Combination types: `uls`, `sls` (characteristic), `freq`, `quasi`, `seismic`, `acc`, `other`.

## Changing and other actions
```
set l3 l4 sec=IPE 360          # re-define (also mat=, type=beam|rib|truss)
delete l3 d2 n7                # deletes; AxisVM renumbers the rest
select l3 d1                   # select in AxisVM (for the user, or for 'sel' filters)
intersect                      # intersect all lines (fixes "overlapping lines" mesh errors); or intersect l1 l2 l5
```

## Example: two-bay frame with slab
```
use mat=S 235
sec COL = HEB 200
sec BM = IPE 300
column 0,0,0 0,0,3.5 sec=COL @ x=0:6:12 y=0,5
beam 0,0,3.5 12,0,3.5 sec=BM @ y=0,5
beam 0,0,3.5 0,5,3.5 sec=BM @ x=0:6:12
slab 0,0,3.5 12,0,3.5 12,5,3.5 0,5,3.5 t=0.2 mat=C30/37
support z=0 fixed
case G self
case Q
load Q d1 pz=-3
combo ULS = 1.35 G + 1.5 Q
```
Then `edit {analyze:'linear'}` and `query {scope:'results', combo:'ULS'}`.

## Other edit fields
`analyze:'linear'` · `mesh:'all size=0.5'` · `import:'path'` (+`import_options`) · `export:'x.dxf'|'x.ifc'` · `open` · `save:'path.axs'` · `new:true` (empty model) · `dry_run:true` (parse only).

## Errors and what is not in the shorthand
A failed line normally changes nothing. If it is marked **NOT clean**, it created objects before the error: `undo {steps:1}` and resend the corrected batch instead of resending only that line. Unknown keys (`beta=`, `from=`, `ey=` …) and unknown words are rejected, never ignored.
Not in the shorthand, use `run`: beta angle, eccentricity, partial or trapezoidal beam loads, temperature, support settlement, semi-rigid (spring) releases, local/beam-relative supports, rigid bodies, links, spring and gap elements, edge hinges, elastic foundations, arcs, load groups, envelopes, nonlinear/vibration/buckling/design.
