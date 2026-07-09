"""
face_test.py — Standalone GreetBot face tester.

Runs ONLY the Pygame eye/mouth graphics engine, with no mic, no Whisper,
no TTS, no network calls. Lets you cycle through emotions and toggle
"talking" mode with the keyboard so you can tune the animation live.

Controls:
    1 = NEUTRAL
    2 = HAPPY
    3 = SAD
    4 = SURPRISED
    5 = THINKING
    6 = CONFUSED
    7 = ANGRY
    8 = EXCITED
    9 = CRYING
    0 = CURIOUS
    T = toggle "talking" mouth animation on/off
    ESC / close window = quit

Run with:
    python face_test.py
"""

import sys
import random
import numpy as np
import pygame

# =====================================================================
#                          FAKE BOT STATE
# =====================================================================
BOT_STATE = {
    "emotion": "NEUTRAL",
}
is_speaking = False  # toggled by pressing T

pygame.display.init()
pygame.font.init()
screen = pygame.display.set_mode((800, 480))
pygame.display.set_caption("GreetBot Face Tester")
clock = pygame.time.Clock()
FONT_UI = pygame.font.SysFont("Courier", 18, bold=True)

# =====================================================================
#             GRAPHICS ENGINE (EVE Wall-E & Anime LED Visor)
# =====================================================================

_blink_state = {"next_blink_at": 0, "blinking_until": 0}


def _update_blink_clock():
    now = pygame.time.get_ticks()
    if now > _blink_state["next_blink_at"] and now > _blink_state["blinking_until"]:
        _blink_state["blinking_until"] = now + 120
        _blink_state["next_blink_at"] = now + random.randint(2500, 6000)


def _is_blinking():
    return pygame.time.get_ticks() < _blink_state["blinking_until"]


def _draw_sparkle(surf, cx, cy, color, size=13):
    """Small 4-point sparkle/star burst, used for the EXCITED expression."""
    pygame.draw.line(surf, color, (cx - size, cy), (cx + size, cy), 3)
    pygame.draw.line(surf, color, (cx, cy - size), (cx, cy + size), 3)
    half = size * 0.55
    pygame.draw.line(surf, color, (cx - half, cy - half), (cx + half, cy + half), 2)
    pygame.draw.line(surf, color, (cx - half, cy + half), (cx + half, cy - half), 2)


# ---- Emotion crossfade transition state ----
_emotion_transition = {"current": "NEUTRAL", "previous": "NEUTRAL", "start": 0, "duration": 250}


def _update_emotion_transition():
    now = pygame.time.get_ticks()
    target = BOT_STATE["emotion"]
    if target != _emotion_transition["current"]:
        _emotion_transition["previous"] = _emotion_transition["current"]
        _emotion_transition["current"] = target
        _emotion_transition["start"] = now


def _get_transition_progress():
    elapsed = pygame.time.get_ticks() - _emotion_transition["start"]
    return min(1.0, elapsed / _emotion_transition["duration"])


def get_blended_eye_surface(side):
    progress = _get_transition_progress()
    to_emotion = _emotion_transition["current"]
    from_emotion = _emotion_transition["previous"]

    if progress >= 1.0 or from_emotion == to_emotion:
        return get_high_res_eye_surface(to_emotion, side)

    from_surf = get_high_res_eye_surface(from_emotion, side)
    to_surf = get_high_res_eye_surface(to_emotion, side)

    blended = pygame.Surface((160, 140), pygame.SRCALPHA)
    from_surf.set_alpha(int((1.0 - progress) * 255))
    to_surf.set_alpha(int(progress * 255))
    blended.blit(from_surf, (0, 0))
    blended.blit(to_surf, (0, 0))
    return blended


def get_high_res_eye_surface(emotion, side):
    """
    Draws a cute, detailed anime eye with EVE Wall-E vibes on a 160x140 transparent surface.
    side: -1 for left eye, 1 for right eye.
    """
    surf = pygame.Surface((160, 140), pygame.SRCALPHA)
    surf.fill((0, 0, 0, 0))  # transparent background

    eye_color = (0, 210, 255)
    white_color = (255, 255, 255)

    cx, cy = 80, 70

    base_w = 90
    base_h = 100
    openness = 1.0
    brow_y_offset = 0
    brow_tilt = 0
    iris_y_offset = 0
    iris_x_offset = 0
    brow_width = 6

    if emotion in ("HAPPY", "EXCITED"):
        scale = 1.22 if emotion == "EXCITED" else 1.0
        points = []
        for angle in range(210, 331, 5):
            rad = np.radians(angle)
            px = cx + 55 * scale * np.cos(rad)
            py = cy + 15 + 35 * scale * np.sin(rad)
            points.append((px, py))
        pygame.draw.lines(surf, eye_color, False, points, 15 if emotion == "EXCITED" else 14)

        lash_x = cx + side * 45 * scale
        lash_y = cy - 5
        pygame.draw.line(surf, eye_color, (lash_x, lash_y), (lash_x + side * 15, lash_y - 10), 8)

        brow_y = cy - 45 - (8 if emotion == "EXCITED" else 0)
        pygame.draw.arc(surf, eye_color, (cx - 45, brow_y, 90, 30), 0.5, 2.6, 6)

        if emotion == "EXCITED":
            _draw_sparkle(surf, cx + side * 62, cy - 32, white_color, size=11)
        return surf

    elif emotion == "SAD":
        # Inner brow corners raised, outer corners drooping (the classic
        # "worried" brow), plus the iris looking down - reads as sad.
        openness = 0.55
        brow_y_offset = 14
        brow_tilt = -side * 22
        iris_y_offset = 16
    elif emotion == "SURPRISED":
        base_w, base_h = 108, 108
        openness = 1.1
        brow_y_offset = -14
    elif emotion == "THINKING":
        if side < 0:
            openness = 0.85
            brow_y_offset = -5
            brow_tilt = -8
        else:
            openness = 0.32
            brow_y_offset = 10
            brow_tilt = 12
    elif emotion == "CONFUSED":
        # One eye wider than the other + brows tilted opposite ways -
        # the classic "wait, what?" mismatched look.
        if side < 0:
            openness = 0.9
            brow_tilt = -18
        else:
            openness = 0.55
            brow_tilt = 22
        brow_y_offset = -8
    elif emotion == "ANGRY":
        # Brows pulled DOWN and angled toward the nose (furrowed "V"
        # across both eyes) - the actual cue that reads as angry.
        openness = 0.5
        brow_y_offset = 10
        brow_tilt = side * 26
        brow_width = 9
    elif emotion == "CRYING":
        # Same drooping worried brow as SAD, but scrunched tighter, with
        # an actual teardrop drawn below the eye.
        openness = 0.42
        brow_y_offset = 16
        brow_tilt = -side * 24
        iris_y_offset = 14
    elif emotion == "CURIOUS":
        # Wide, alert eyes with one eyebrow raised, both irises glancing
        # to the same side - like tracking something with interest.
        openness = 0.95
        if side < 0:
            brow_y_offset = -16
            brow_tilt = -10
        else:
            brow_y_offset = -4
            brow_tilt = 6
        iris_x_offset = 14 * side
    else:
        openness = 1.0

    if _is_blinking():
        openness = 0.02

    lid_pts = []
    for angle in range(190, 351, 5):
        rad = np.radians(angle)
        px = cx + (base_w // 2 + 5) * np.cos(rad)
        py = cy - (base_h // 2) * openness * 0.2 + (base_h // 2) * openness * np.sin(rad)
        lid_pts.append((px, py))

    tilt_deg = 0
    if emotion == "NEUTRAL":
        tilt_deg = -8 * side
    elif emotion == "SAD":
        tilt_deg = -18 * side
    elif emotion == "THINKING":
        tilt_deg = -10 if side < 0 else 12
    elif emotion == "CONFUSED":
        tilt_deg = -14 if side < 0 else 16
    elif emotion == "ANGRY":
        tilt_deg = 10 * side
    elif emotion == "CRYING":
        tilt_deg = -20 * side
    elif emotion == "CURIOUS":
        tilt_deg = 6 * side

    def rotate_point(pt, angle_deg, center):
        angle_rad = np.radians(angle_deg)
        ox, oy = center
        px, py = pt
        qx = ox + np.cos(angle_rad) * (px - ox) - np.sin(angle_rad) * (py - oy)
        qy = oy + np.sin(angle_rad) * (px - ox) + np.cos(angle_rad) * (py - oy)
        return int(qx), int(qy)

    rotated_lid = [rotate_point(p, tilt_deg, (cx, cy)) for p in lid_pts]
    pygame.draw.lines(surf, eye_color, False, rotated_lid, 10)

    outer_idx = -1 if side > 0 else 0
    outer_pt = rotated_lid[outer_idx]
    pygame.draw.line(surf, eye_color, outer_pt, (outer_pt[0] + side * 16, outer_pt[1] - 8), 8)

    eye_h = int(base_h * openness)
    if eye_h > 15:
        iris_w = int(base_w * 0.72)
        iris_h = int(eye_h * 0.85)

        iris_surf = pygame.Surface((iris_w, iris_h), pygame.SRCALPHA)
        iris_surf.fill((0, 0, 0, 0))

        pygame.draw.ellipse(iris_surf, eye_color, (0, 0, iris_w, iris_h))

        hl1_cx = int(iris_w * 0.35)
        hl1_cy = int(iris_h * 0.3)
        hl1_r = int(min(iris_w, iris_h) * 0.18)
        pygame.draw.circle(iris_surf, white_color, (hl1_cx, hl1_cy), hl1_r)

        hl2_cx = int(iris_w * 0.7)
        hl2_cy = int(iris_h * 0.7)
        hl2_r = int(min(iris_w, iris_h) * 0.09)
        pygame.draw.circle(iris_surf, white_color, (hl2_cx, hl2_cy), hl2_r)

        rotated_iris = pygame.transform.rotate(iris_surf, -tilt_deg)
        r_rect = rotated_iris.get_rect()
        r_rect.center = (cx + iris_x_offset, cy + iris_y_offset)
        surf.blit(rotated_iris, r_rect)

    pygame.draw.lines(surf, eye_color, False, rotated_lid, 8)

    brow_y = cy - base_h * 0.6 + brow_y_offset
    brow_half = base_w * 0.5
    brow_p1 = (cx - brow_half, brow_y + brow_tilt)
    brow_p2 = (cx + brow_half, brow_y - brow_tilt)
    rot_p1 = rotate_point(brow_p1, tilt_deg * 0.5, (cx, cy))
    rot_p2 = rotate_point(brow_p2, tilt_deg * 0.5, (cx, cy))
    pygame.draw.line(surf, eye_color, rot_p1, rot_p2, brow_width)

    if emotion == "CRYING":
        tear_x = cx + side * 12
        tear_top_y = cy + int(base_h * openness * 0.35)
        tear_pts = [
            (tear_x, tear_top_y),
            (tear_x - 7, tear_top_y + 22),
            (tear_x, tear_top_y + 38),
            (tear_x + 7, tear_top_y + 22),
        ]
        pygame.draw.polygon(surf, (60, 170, 255), tear_pts)
        pygame.draw.polygon(surf, (180, 230, 255), tear_pts, 2)

    return surf


def draw_led_grid(dest_screen, src_surf, cx, cy, grid_spacing=4):
    w, h = src_surf.get_size()
    grid_w = w // grid_spacing
    grid_h = h // grid_spacing

    low_res = pygame.transform.scale(src_surf, (grid_w, grid_h))

    start_x = cx - (grid_w * grid_spacing) // 2
    start_y = cy - (grid_h * grid_spacing) // 2

    for y in range(grid_h):
        for x in range(grid_w):
            color = low_res.get_at((x, y))
            if color.a > 0 and (color.r > 10 or color.g > 10 or color.b > 10):
                px = start_x + x * grid_spacing + grid_spacing // 2
                py = start_y + y * grid_spacing + grid_spacing // 2

                is_highlight = (color.r > 220 and color.g > 220 and color.b > 220)
                if is_highlight:
                    core_color = (255, 255, 255)
                    glow_color = (0, 100, 220)
                else:
                    core_color = (130, 240, 255)
                    glow_color = (0, 80, 180)

                pygame.draw.circle(dest_screen, glow_color, (px, py), grid_spacing * 0.75)
                pygame.draw.circle(dest_screen, core_color, (px, py), grid_spacing * 0.38)


def draw_glowing_mouth(screen, cx, cy, emotion, talking=False):
    color = (130, 240, 255)
    glow_color = (0, 80, 180)

    if talking:
        wobble = abs(np.sin(pygame.time.get_ticks() / 90.0))
        mouth_h = int(6 + wobble * 22)
        rect = pygame.Rect(cx - 26, cy - mouth_h // 2, 52, mouth_h)
        pygame.draw.ellipse(screen, glow_color, rect, 8)
        pygame.draw.ellipse(screen, color, rect, 4)
        return

    if emotion == "HAPPY":
        rect = pygame.Rect(cx - 30, cy - 10, 60, 30)
        pygame.draw.arc(screen, glow_color, rect, 3.5, 5.9, 8)
        pygame.draw.arc(screen, color, rect, 3.5, 5.9, 4)
    elif emotion == "SAD":
        rect = pygame.Rect(cx - 24, cy, 48, 24)
        pygame.draw.arc(screen, glow_color, rect, 0.4, 2.7, 8)
        pygame.draw.arc(screen, color, rect, 0.4, 2.7, 4)
    elif emotion == "SURPRISED":
        pygame.draw.ellipse(screen, glow_color, pygame.Rect(cx - 12, cy - 8, 24, 20), 8)
        pygame.draw.ellipse(screen, color, pygame.Rect(cx - 12, cy - 8, 24, 20), 4)
    elif emotion == "THINKING":
        pygame.draw.line(screen, glow_color, (cx - 15, cy + 3), (cx + 15, cy - 3), 8)
        pygame.draw.line(screen, color, (cx - 15, cy + 3), (cx + 15, cy - 3), 4)
    elif emotion == "CONFUSED":
        wavy_pts = [(cx - 24, cy), (cx - 12, cy + 8), (cx, cy - 4), (cx + 12, cy + 8), (cx + 24, cy)]
        pygame.draw.lines(screen, glow_color, False, wavy_pts, 8)
        pygame.draw.lines(screen, color, False, wavy_pts, 4)
    elif emotion == "ANGRY":
        pygame.draw.line(screen, glow_color, (cx - 20, cy), (cx + 20, cy), 10)
        pygame.draw.line(screen, color, (cx - 20, cy), (cx + 20, cy), 6)
    elif emotion == "EXCITED":
        # Big open "O" grin - wider and rounder than HAPPY's simple curve.
        pygame.draw.ellipse(screen, glow_color, pygame.Rect(cx - 22, cy - 14, 44, 32), 8)
        pygame.draw.ellipse(screen, color, pygame.Rect(cx - 22, cy - 14, 44, 32), 4)
    elif emotion == "CRYING":
        # Tighter, more scrunched frown than plain SAD.
        rect = pygame.Rect(cx - 18, cy + 2, 36, 20)
        pygame.draw.arc(screen, glow_color, rect, 0.5, 2.6, 8)
        pygame.draw.arc(screen, color, rect, 0.5, 2.6, 4)
    elif emotion == "CURIOUS":
        # Small, slightly puckered "o" - inquisitive, not shocked-wide.
        pygame.draw.ellipse(screen, glow_color, pygame.Rect(cx - 9, cy - 6, 18, 16), 6)
        pygame.draw.ellipse(screen, color, pygame.Rect(cx - 9, cy - 6, 18, 16), 3)
    else:
        pygame.draw.line(screen, glow_color, (cx - 18, cy), (cx + 18, cy), 8)
        pygame.draw.line(screen, color, (cx - 18, cy), (cx + 18, cy), 4)


def draw_visor_scanlines(screen, width, visor_h):
    for y in range(0, visor_h, 4):
        pygame.draw.line(screen, (12, 16, 32), (0, y), (width, y), 1)


def draw_interface():
    screen.fill((10, 12, 20))
    draw_visor_scanlines(screen, 800, 370)

    _update_blink_clock()
    _update_emotion_transition()
    emotion = _emotion_transition["current"]

    left_eye_center = (250, 160)
    right_eye_center = (550, 160)
    mouth_center = (400, 255)

    left_eye_surf = get_blended_eye_surface(side=-1)
    right_eye_surf = get_blended_eye_surface(side=1)

    draw_led_grid(screen, left_eye_surf, left_eye_center[0], left_eye_center[1], grid_spacing=4)
    draw_led_grid(screen, right_eye_surf, right_eye_center[0], right_eye_center[1], grid_spacing=4)

    draw_glowing_mouth(screen, mouth_center[0], mouth_center[1], emotion, talking=is_speaking)

    # Bottom control panel / instructions
    pygame.draw.rect(screen, (16, 20, 35), (0, 370, 800, 110))
    pygame.draw.line(screen, (35, 42, 68), (0, 370), (800, 370), 2)

    accent_color = (0, 210, 255) if emotion != "SAD" else (255, 60, 100)
    if emotion == "THINKING":
        accent_color = (255, 200, 0)

    label_emotion = FONT_UI.render(f"CURRENT EMOTION: {emotion}   |   TALKING: {is_speaking}", True, accent_color)
    label_controls = FONT_UI.render(
        "1-7=emotions 8=EXCITED 9=CRYING 0=CURIOUS  T=talk  ESC=quit",
        True, (170, 180, 210)
    )

    screen.blit(label_emotion, (20, 390))
    screen.blit(label_controls, (20, 425))

    pygame.display.flip()


def main():
    global is_speaking
    while True:
        draw_interface()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    pygame.quit()
                    sys.exit()
                elif event.key == pygame.K_1:
                    BOT_STATE["emotion"] = "NEUTRAL"
                elif event.key == pygame.K_2:
                    BOT_STATE["emotion"] = "HAPPY"
                elif event.key == pygame.K_3:
                    BOT_STATE["emotion"] = "SAD"
                elif event.key == pygame.K_4:
                    BOT_STATE["emotion"] = "SURPRISED"
                elif event.key == pygame.K_5:
                    BOT_STATE["emotion"] = "THINKING"
                elif event.key == pygame.K_6:
                    BOT_STATE["emotion"] = "CONFUSED"
                elif event.key == pygame.K_7:
                    BOT_STATE["emotion"] = "ANGRY"
                elif event.key == pygame.K_8:
                    BOT_STATE["emotion"] = "EXCITED"
                elif event.key == pygame.K_9:
                    BOT_STATE["emotion"] = "CRYING"
                elif event.key == pygame.K_0:
                    BOT_STATE["emotion"] = "CURIOUS"
                elif event.key == pygame.K_t:
                    is_speaking = not is_speaking
        clock.tick(30)


if __name__ == "__main__":
    main()