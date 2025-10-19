import numpy as np
from pathlib import Path
import json, copy
REQ = {"Fuss_L","Fuss_R","Hüfte","Hals","Kopf","Hand_L","Hand_R"}
EPS = 1e-6


def write_js(name: str, obj: dict, varname: str):
    js = f"window.{varname} = {json.dumps(obj, ensure_ascii=False)};\n"
    Path(name).write_text(js, encoding="utf-8")


def build_stickman(points: dict, color: str):

    # choose shape
    if "leftShoulder" in points or "rightShoulder" in points:
        shape = v3_shape
    elif "leftArm" in points or "rightArm" in points:
        shape = v1_shape
    else:
        raise ValueError("Cannot detect skeleton: need shoulders (v3) or arms (v1).")

    # require all nodes for chosen shape
    req = set(shape.keys()) | {c for cs in shape.values() for c in cs}
    miss = sorted(req - set(points))
    if miss:
        raise ValueError(f"missing: {miss}")

    v = points
    lines = [[v[a], v[b]] for a, cs in shape.items() for b in cs]
    return {"color": color, "lines": lines}




# für alle
base_body = {
    "height": 1.50
}
base_proportions = {
    "div": 7.5,  # the face is about 2/15 of the body height
    "base": {
        "neck": 2.5,
        "leg": 2.5,
        "hip": 0.5
    },
    "neck": {
        "head": 1.5,  # head=forehead
        "shoulder": 1,
        "arm": 3  # middle of forearm
    },
    "hip": {
        "knee": 1.5,
    },
    "knee": {
        "foot": 2  # foot=ankle
    },
    "head":{
        "chin": 1
    },
    "shoulder": {
        "elbow": 1.5
    },
    "elbow": {
        "hand": 1.5  # hand=wrist
    },
    "foot":{
        "toe": 1
    },
    "hand": {
        "finger": 0.5  # fingers a little bent
    }
}


# removes "left" or "right"
def clean_joint_name(name_in):
    clean = name_in.lower()
    for dirt in ["left", "right", "up", "down", "fw", "bw", "out"]:
        clean = clean.replace(dirt, "")
    return clean.strip()

def get_dir(key: str):
    k = key[4:].lower()
    if any(x in k for x in ["up", "down", "roll"]):
        return 0  # up/down
    if any(x in k for x in ["fw", "bw", "forward", "back"]):
        return 1   # forward/backward
    if any(x in k for x in ["out", "in", "left", "right"]):
        return 2   # left/right
    return None



def rotated_right(new_up, angle_deg):
    # normalize input
    new_up = np.array(new_up, dtype=float)
    new_up /= np.linalg.norm(new_up)

    # define base vectors
    old_up = np.array([0, 1, 0], dtype=float)
    x = np.array([1, 0, 0], dtype=float)  # old right

    # rotation from old_up to new_up
    axis = np.cross(old_up, new_up)
    if np.linalg.norm(axis) < 1e-8:
        rot_to_new_up = np.eye(3)
    else:
        axis /= np.linalg.norm(axis)
        angle = np.arccos(np.clip(np.dot(old_up, new_up), -1, 1))
        K = np.array([[0, -axis[2], axis[1]],
                      [axis[2], 0, -axis[0]],
                      [-axis[1], axis[0], 0]])
        rot_to_new_up = np.eye(3) + np.sin(angle)*K + (1-np.cos(angle))*(K@K)

    # apply to right vector
    right = rot_to_new_up @ x

    # rotate around new_up by angle_deg
    a = np.deg2rad(angle_deg)
    K2 = np.array([[0, -new_up[2], new_up[1]],
                   [new_up[2], 0, -new_up[0]],
                   [-new_up[1], new_up[0], 0]])
    rot_around_up = np.eye(3) + np.sin(a)*K2 + (1-np.cos(a))*(K2@K2)

    # final right vector
    new_right = rot_around_up @ right
    return new_right / np.linalg.norm(new_right)



def _rodrigues(a, ang):
    a = np.array(a, float); n = np.linalg.norm(a)
    if n<1e-12: return np.eye(3)
    a/=n; x,y,z=a; s,c=np.sin(ang),np.cos(ang)
    K=np.array([[0,-z,y],[z,0,-x],[-y,x,0]])
    return np.eye(3)+s*K+(1-c)*(K@K)

def rotate(old_vec, spine, rotation, transformation):
    old_up=np.array([0,1,0.]); spine=np.array(spine,float); spine/=np.linalg.norm(spine)
    axis=np.cross(old_up,spine); ang=np.arccos(np.clip(np.dot(old_up,spine),-1,1))
    R_up2sp=_rodrigues(axis,ang)
    R_yaw=_rodrigues(spine, np.deg2rad(rotation))
    R_frame=R_yaw@R_up2sp
    v_local=R_frame.T@np.array(old_vec,float)

    # order: up/down (about local x), fw/bw (about local z), left/right (about local y)
    ud,fb,lr=[np.deg2rad(a) for a in (transformation+[0,0,0])[:3]]
    # convention tweak: negative ud = tilt down
    Rx=np.array([[1,0,0],[0,np.cos(-ud),-np.sin(-ud)],[0,np.sin(-ud),np.cos(-ud)]])
    Rz=np.array([[np.cos(fb),-np.sin(fb),0],[np.sin(fb),np.cos(fb),0],[0,0,1]])
    Ry=np.array([[np.cos(lr),0,np.sin(lr)],[0,1,0],[-np.sin(lr),0,np.cos(lr)]])
    v_local2=Ry@Rz@Rx@v_local
    new_vec = R_frame @ v_local2
    new_vec = new_vec / np.linalg.norm(new_vec)
    return new_vec

# Test (y=up): forward -> 90° down => down
vec = rotate([0,0,1], [0,1,0], 0, [0,90,0])
#print(vec)  # ≈ [0, -1, 0]



# v3
v3_shape = {
    "base": ["neck", "leftHip", "rightHip"],
    "neck": ["head", "leftShoulder", "rightShoulder"],
    "head": ["chin"],
    "leftShoulder": ["leftElbow"],
    "leftElbow": ["leftHand"],
    "leftHand": ["leftFinger"],
    "leftHip": ["leftKnee"],
    "leftKnee": ["leftFoot"],
    "leftFoot": ["leftToe"],
    "rightShoulder": ["rightElbow"],
    "rightElbow": ["rightHand"],
    "rightHand": ["rightFinger"],
    "rightHip": ["rightKnee"],
    "rightKnee": ["rightFoot"],
    "rightFoot": ["rightToe"]
}
base_figure_v3_sit_uv = {
    "base": [0, 0, 0],
    "neck": [-0.70710678118, 0.70710678118, 0],
    "head": [-0.342, 0.94, 0],
    "chin": [-0.70710678118, 0.70710678118, 0],
    "leftHip": [0, 0, 1],
    "rightHip": [0, 0, -1],
    "leftShoulder": [0, 0, 1],
    "rightShoulder": [0, 0, -1],
    "leftElbow": [0.70710678118, 0, 0.70710678118],
    "rightElbow": [0.70710678118, 0, -0.70710678118],
    "leftHand": [0.70710678118, 0.70710678118, 0],
    "rightHand": [0.70710678118, 0.70710678118, 0],
    "leftFinger": [0.70710678118, 0.70710678118, 0],
    "rightFinger": [0.70710678118, 0.70710678118, 0],
    "leftKnee": [-0.3333333333, 0.3333333333, 0.3333333333],
    "rightKnee": [0.3333333333, 0.3333333333, 0.3333333333],
    "rightFoot": [0.70710678118, -0.70710678118, 0],
    "leftFoot": [0.70710678118, -0.70710678118, 0],
    "leftToe": [0.70710678118, 0.70710678118, 0],
    "rightToe": [0.70710678118, 0.70710678118, 0]
}

# v1
v1_shape = {
    "base": ["neck", "leftLeg", "rightLeg"],
    "neck": ["head", "leftArm", "rightArm"]
}
figure_v1_stand_uv = {
    "base": [0, 1, 0],          #flies probably!
    "neck": [0, 1, 0],
    "leftLeg": [-0.342, -0.94, 0],
    "rightLeg": [0.342, -0.94, 0],
    "head": [0, 1, 0],
    "leftArm": [0, 0, 1],
    "rightArm": [0, 0, -1]
}

base_figure_v1_sit_uv = {
    "base": [0, 0, 0],
    "neck": [-0.70710678118, 0.70710678118, 0],
    "head": [-0.70710678118, 0.70710678118, 0],
    "leftArm": [0, 0.70710678118, 0.70710678118],
    "rightArm": [0, 0.70710678118, -0.70710678118],
    "leftLeg": [0.70710678118, 0, 0.70710678118],
    "rightLeg": [0.70710678118, 0, -0.70710678118]
}

stickman_v1_16dof_moveto_sit = {
    "base": [0, 0, 0],
    "neck": [0, 0, 0],
    "rotation": 0,
    "headRoll": 0,
    "leftArmUpDown": 0,
    "leftArmFwBw": 0,
    "rightArmUpDown": 0,
    "rightArmFwBw": 0,
    "leftLegOut": 0,
    "leftLegFwBw": 0,
    "rightLegOut": 0,
    "rightLegFwBw": 0
}

stickman_v1_16dof_moveto_stand = {
    "base": [0, 1, 0], # problem Y: ev. kollision mit MATTE
    "neck": [0, 1, 0],
    "rotation": 0,
    "headRoll": 0,
    "leftArmUpDown": -90,
    "leftArmFwBw": 0,
    "rightArmUpDown": -90,
    "rightArmFwBw": 0,
    "leftLegOut": -10,
    "leftLegFwBw": -90,
    "rightLegOut": -10,
    "rightLegFwBw": -90
}


def dimToUv(figure, base_figure, debug=False):
    uv_figure = {
        "base": figure["base"],
        "neck": figure["neck"]
    }
    for base_key in base_figure.keys():
        for new_key in figure.keys():
            t = [0,0,0]
            if new_key not in ["base", "neck", "rotation"]:
                if debug:
                    print(f"base key: {base_key}")
                    print(f"new key: {new_key}")
                if clean_joint_name(new_key) in base_key:
                    t[get_dir(new_key)] = figure[new_key]
        uv_figure[base_key] = rotate(base_figure[base_key], base_figure["neck"], figure["rotation"], t)
    uv_figure = {k: np.nan_to_num(v).tolist() for k, v in uv_figure.items()}
    return uv_figure


#testing dimTouV
new = dimToUv(stickman_v1_16dof_moveto_stand, base_figure_v1_sit_uv)
for j in new:
    print(j)

# getestet für v1
def uvTo3d(uv_figure, body_shape=None, body=None, proportions=None, orig=None, debug=False):
    if orig is None:
        orig = [0,0,0]
    if proportions is None:
        proportions = base_proportions
    if body is None:
        body = base_body
    if body_shape is None:
        body_shape = v1_shape
    uv_figure["orig"] = orig
    body_3d = {
        "base": uv_figure["base"]
    }
    for i in body_shape.keys():
        if debug:
            print(f"i is {i}")
        for j in body_shape[i]:
            if debug:
                print(f"    j is {j}")
            for n in uv_figure[j]:
                if debug:
                    print(f"        n is {n}")
            bone_len = float(proportions[clean_joint_name(i)][clean_joint_name(j)]) / proportions["div"] * float(body["height"])
            body_3d[j] = [body_3d[i][n] + uv_figure[j][n] * bone_len for n in range(3)]
    return body_3d


# testing uvTo3d
stick_3d = uvTo3d(base_figure_v1_sit_uv)
stick_3d = uvTo3d(base_figure_v3_sit_uv, body_shape=v3_shape)
for joint in stick_3d.keys():
    print(joint + str(stick_3d[joint]))


"""
# todo:
ausrichtung komplett von situation trennen


"""


def not_used______stickman_figure(moves, base_figure=None):
    if base_figure is None:
        base_figure = base_figure_v1_sit_uv
    new_figure = base_figure.copy()
    for move in moves:
        for my_joint in new_figure.keys():
            if my_joint != "base":
                pass

        #base_figure
