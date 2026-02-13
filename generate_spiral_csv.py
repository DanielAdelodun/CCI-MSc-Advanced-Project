"""
Blender Python script — flight path as colored 3D curve per mode

Creates a 3D curve with a small bevel, splits the path by mode, assigns a distinct material color for each mode,
and exports CSV with index, x, y, z, mode, r, g, b.
"""

import bpy
import math
import csv
import os

# ---------------------- CONFIG ----------------------
h_start = 15.0
spiral_height = 10.0
turns = 3
start_radius = 10.0
end_radius = 0.0
spacing = 0.03
move_spacing = 0.1
start_angle = 0.0
hold_time = 2.0

time_step = 0.1
bevel_depth = 0.1
export_csv = True
csv_filename = "flight_points_colored_curve.csv"
object_name_prefix = "FlightCurve"

# ---------------- Spiral function ----------------
def spiral_position(t):
    r = (1 - t) * start_radius + t * end_radius
    th = - (2 * math.pi * turns) * t + start_angle
    return (
        r * math.cos(th),
        r * math.sin(th),
        h_start + spiral_height * t,
    )

def dist(a, b):
    return math.dist(a, b)

def generate_move_points(p0, p1, step_dist):
    pts = []
    total = dist(p0, p1)
    if total == 0:
        return [p0]
    steps = int(total / step_dist)
    for i in range(steps + 1):
        t = i / steps
        x = p0[0] + (p1[0] - p0[0]) * t
        y = p0[1] + (p1[1] - p0[1]) * t
        z = p0[2] + (p1[2] - p0[2]) * t
        pts.append((x, y, z))
    return pts

def generate_spiral():
    pts = []
    t = 0.0
    prev = spiral_position(0.0)
    pts.append(prev)
    while t < 1.0:
        dt = 0.0001
        while True:
            cand_t = t + dt
            if cand_t > 1.0:
                return pts
            cand = spiral_position(cand_t)
            if dist(prev, cand) >= spacing:
                pts.append(cand)
                prev = cand
                t = cand_t
                break
            dt *= 1.5
    return pts

def hold_points(p, seconds):
    count = int(seconds / time_step)
    return [p]*count

# ---------------- Mode colors ----------------
mode_colors = {
    10: (1,0,0),    # red rise
    20: (1,0.5,0),  # orange hold rise
    30: (0,1,0),    # green move
    40: (0,1,1),    # cyan hold start
    50: (0,0,1),    # blue spiral
    60: (0.5,0,0.5),# purple hold end
    70: (0,0,0),    # black return
}

# ---------------- Build trajectory per mode ----------------
trajectory = []  # tuples: (points_list, mode)

# Mode 10 rise
rise = generate_move_points((0,0,0), (0,0,h_start), move_spacing)
trajectory.append((rise, 10))

# Mode 20 hold rise
h20 = hold_points((0,0,h_start), hold_time)
trajectory.append((h20, 20))

# Spiral points
spiral_pts = generate_spiral()
start_pt = spiral_pts[0]

# Mode 30 move to start
m30 = generate_move_points((0,0,h_start), start_pt, move_spacing)
trajectory.append((m30, 30))

# Mode 40 hold start
h40 = hold_points(start_pt, hold_time)
trajectory.append((h40, 40))

# Mode 50 spiral trace
trajectory.append((spiral_pts, 50))

# Mode 60 hold end
end_pt = spiral_pts[-1]
h60 = hold_points(end_pt, hold_time)
trajectory.append((h60, 60))

# Mode 70 return home
m70 = generate_move_points(end_pt, (0,0,h_start), move_spacing)
trajectory.append((m70, 70))

# ---------------- Create materials ----------------
materials = {}
for mode, col in mode_colors.items():
    mat_name = f"Mode_{mode}_Mat"
    if mat_name in bpy.data.materials:
        mat = bpy.data.materials[mat_name]
    else:
        mat = bpy.data.materials.new(mat_name)
        mat.diffuse_color = (*col,1.0)
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs['Base Color'].default_value = (*col,1.0)
    materials[mode] = mat

# ---------------- Create curve object ----------------
for idx, (pts_list, mode) in enumerate(trajectory):
    if len(pts_list) < 2:
        continue
    curve_name = f"{object_name_prefix}_Mode{mode}"
    if curve_name in bpy.data.objects:
        bpy.data.objects.remove(bpy.data.objects[curve_name], do_unlink=True)
    curve_data = bpy.data.curves.new(curve_name + "_Data", 'CURVE')
    curve_data.dimensions = '3D'
    spline = curve_data.splines.new('POLY')
    spline.points.add(len(pts_list)-1)
    for i,(x,y,z) in enumerate(pts_list):
        spline.points[i].co = (x,y,z,1)
    curve_data.bevel_depth = bevel_depth
    curve_obj = bpy.data.objects.new(curve_name, curve_data)
    curve_obj.data.materials.append(materials[mode])
    bpy.context.collection.objects.link(curve_obj)

# ---------------- Export CSV ----------------
if export_csv:
    all_pts = []
    all_modes = []
    all_colors = []
    for pts_list, mode in trajectory:
        all_pts += pts_list
        all_modes += [mode]*len(pts_list)
        all_colors += [mode_colors[mode]]*len(pts_list)

    if bpy.data.is_saved:
        base = bpy.path.abspath('//')
        csv_path = os.path.join(base, csv_filename)
    else:
        csv_path = os.path.join(os.path.expanduser('~'), csv_filename)

    with open(csv_path,'w',newline='') as f:
        w = csv.writer(f)
        w.writerow(["index","x","y","z","mode","r","g","b"])
        for i,(p,m,col) in enumerate(zip(all_pts, all_modes, all_colors)):
            w.writerow([i,p[0],p[1],p[2],m,col[0],col[1],col[2]])

print(f"Flight curve created and CSV exported: {csv_path}")
