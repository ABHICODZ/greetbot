import os
import sys
import subprocess
import threading
import time
import wave
import random
import numpy as np
import pygame
import brain

# =====================================================================
#                          ROBOT CENTRAL CONTROLS
# =====================================================================
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(_SCRIPT_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

# Select dynamic RAM disk paths to minimize disk I/O latency and prevent wear
if os.path.exists("/dev/shm"):
    RAM_DIR = "/dev/shm"
else:
    RAM_DIR = "/tmp"

CONFIG = {
    "BOT_NAME": brain.CONFIG["BOT_NAME"],
    "WHISPER_PATH": os.path.join(DATA_DIR, "whisper_models"),
    "TEMP_WAV_PATH": os.path.join(RAM_DIR, "temp_voice.wav"),
    "PIPER_MODEL_PATH": os.path.join(DATA_DIR, "piper_voices", "en_US-amy-medium.onnx"),
    "TEMP_TTS_WAV_PATH": os.path.join(RAM_DIR, "temp_tts_out.wav"),
    "WHISPER_MODEL": os.environ.get("WHISPER_MODEL", "tiny.en"),
}
os.makedirs(CONFIG["WHISPER_PATH"], exist_ok=True)

from faster_whisper import WhisperModel

# --- VOICE ACTIVITY DETECTION TUNING ---
VAD_SAMPLE_RATE = 16000
VAD_CHUNK_MS = 30
VAD_CHUNK_SAMPLES = int(VAD_SAMPLE_RATE * VAD_CHUNK_MS / 1000)
VAD_SPEECH_THRESHOLD = int(os.environ.get("VAD_SPEECH_THRESHOLD", 350))
VAD_SILENCE_MS_TO_STOP = 900
VAD_MAX_WAIT_FOR_SPEECH_S = 8
VAD_MAX_UTTERANCE_S = 15
VAD_MIN_SPEECH_MS = 300
POST_SPEAK_COOLDOWN_S = 0.6

BOT_STATE = {
    "emotion": "NEUTRAL",
    "user_transcript": "System Initializing...",
    "bot_response": "",
    "status_msg": "System Booting"
}
is_speaking = False

pygame.display.init()
pygame.font.init()
screen = pygame.display.set_mode((800, 480))
pygame.display.set_caption("Robo System Control Core (Pi)")
clock = pygame.time.Clock()
FONT_UI = pygame.font.SysFont("Courier", 16, bold=True)

# =====================================================================
#                     MIC INPUT (PipeWire subprocess)
# =====================================================================

def ensure_mic_ready():
    """
    On Linux/Pi, we check if pw-record is available and if the PipeWire
    daemon is running.
    """
    BOT_STATE["status_msg"] = "Checking Mic Access..."
    try:
        subprocess.run(["which", "pw-record"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        res = subprocess.run(["pgrep", "-x", "pipewire"], capture_output=True)
        if res.returncode != 0:
            print("\n[MIC FAULT]: pipewire daemon is not running. Check PipeWire system status.")
            return False
        return True
    except Exception as e:
        print(f"\n[MIC FAULT]: pw-record is missing or PipeWire is inactive: {e}")
        return False


def capture_audio_clip():
    """
    Records raw PCM via pw-record subprocess, analyzing RMS chunks for VAD.
    Writes the final clip as a WAV file to CONFIG["TEMP_WAV_PATH"].
    """
    # pw-record command to output raw s16le PCM to stdout
    cmd = ["pw-record", "--record", "--rate", str(VAD_SAMPLE_RATE), 
           "--channels", "1", "--format", "s16", "--latency", "30ms", "-"]
    
    frames = []
    triggered = False
    silence_ms_accum = 0
    speech_ms_accum = 0
    start_time = time.time()
    
    proc = None
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        
        while True:
            elapsed = time.time() - start_time
            if not triggered and elapsed > VAD_MAX_WAIT_FOR_SPEECH_S:
                break
            if triggered and elapsed > VAD_MAX_UTTERANCE_S:
                break
                
            chunk_bytes = proc.stdout.read(VAD_CHUNK_SAMPLES * 2) # s16 is 2 bytes/sample
            if not chunk_bytes:
                break
                
            samples = np.frombuffer(chunk_bytes, dtype=np.int16)
            if len(samples) == 0:
                continue
                
            rms = float(np.sqrt(np.mean(samples.astype(np.float32) ** 2)))
            is_speech = rms > VAD_SPEECH_THRESHOLD
            
            if not triggered:
                if is_speech:
                    triggered = True
                    BOT_STATE["status_msg"] = "Hearing You..."
                    frames.append(samples.copy())
                    speech_ms_accum += VAD_CHUNK_MS
                continue
                
            frames.append(samples.copy())
            if is_speech:
                silence_ms_accum = 0
                speech_ms_accum += VAD_CHUNK_MS
            else:
                silence_ms_accum += VAD_CHUNK_MS
                if silence_ms_accum >= VAD_SILENCE_MS_TO_STOP:
                    break
                    
        proc.terminate()
        proc.wait(timeout=1.0)
        
        if not triggered or speech_ms_accum < VAD_MIN_SPEECH_MS:
            return False
            
        raw_audio = np.concatenate(frames).astype(np.int16).tobytes()
        with wave.open(CONFIG["TEMP_WAV_PATH"], "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(VAD_SAMPLE_RATE)
            wf.writeframes(raw_audio)
        return True
        
    except Exception as e:
        print(f"\n[CAPTURE FAULT]: {e}")
        if proc:
            try:
                proc.kill()
            except:
                pass
        return False


# =====================================================================
#                     TTS OUTPUT (Piper -> paplay, espeak fallback)
# =====================================================================

def speak_text(text):
    global is_speaking
    is_speaking = True
    BOT_STATE["status_msg"] = "Vocalizing Output..."

    piper_ok = False
    if os.path.exists(CONFIG["PIPER_MODEL_PATH"]):
        try:
            gen = subprocess.run(
                ["piper", "--model", CONFIG["PIPER_MODEL_PATH"],
                 "--output_file", CONFIG["TEMP_TTS_WAV_PATH"]],
                input=text, text=True, capture_output=True, timeout=15
            )
            if gen.returncode == 0 and os.path.exists(CONFIG["TEMP_TTS_WAV_PATH"]):
                subprocess.run(["paplay", CONFIG["TEMP_TTS_WAV_PATH"]], check=True, timeout=20)
                piper_ok = True
            else:
                print(f"\n[Piper TTS Error]: {gen.stderr.strip()}")
        except Exception as e:
            print(f"\n[Piper TTS Error]: {e}")

    if not piper_ok:
        try:
            subprocess.run(["espeak", text], check=True)
        except Exception as e:
            print(f"\n[TTS Fallback Error]: {e}")

    is_speaking = False
    BOT_STATE["emotion"] = "NEUTRAL"
    BOT_STATE["status_msg"] = "Listening Active"
    time.sleep(POST_SPEAK_COOLDOWN_S)


# =====================================================================
#                          CORE SUBSYSTEMS
# =====================================================================

def query_robot_brain(user_input):
    BOT_STATE["emotion"] = "THINKING"
    BOT_STATE["status_msg"] = f"Thinking ({brain.CONFIG['BACKEND'].upper()})..."
    try:
        response_text, emotion = brain.query_ollama(user_input)
        BOT_STATE["bot_response"] = response_text
        BOT_STATE["emotion"] = emotion
        speak_text(response_text)
    except Exception as e:
        print(f"\n[BRAIN FAULT]: {e}")
        BOT_STATE["emotion"] = "SAD"
        BOT_STATE["bot_response"] = "Sorry, my thinking engine had a problem."
        speak_text(BOT_STATE["bot_response"])


def voice_assistant_worker():
    BOT_STATE["status_msg"] = f"Loading Whisper ({CONFIG['WHISPER_MODEL']})..."
    try:
        model = WhisperModel(
            CONFIG["WHISPER_MODEL"],
            device="cpu",
            compute_type="int8",
            download_root=CONFIG["WHISPER_PATH"]
        )
    except Exception as e:
        print(f"\n[Model Init Fault]: {e}")
        BOT_STATE["status_msg"] = "Whisper Fail"
        return

    mic_ready = False
    for attempt in range(5):
        if ensure_mic_ready():
            mic_ready = True
            break
        BOT_STATE["status_msg"] = f"Mic Retry {attempt + 1}/5..."
        time.sleep(1.5)

    if not mic_ready:
        BOT_STATE["status_msg"] = "MIC FAILED"
        BOT_STATE["user_transcript"] = "Could not verify PipeWire input device."
        while True:
            time.sleep(5)

    BOT_STATE["status_msg"] = "Listening Active"
    BOT_STATE["user_transcript"] = f"System Ready (Whisper {CONFIG['WHISPER_MODEL']}). Speak!"

    while True:
        if is_speaking:
            time.sleep(0.4)
            continue

        try:
            ok = capture_audio_clip()

            if not ok or not os.path.exists(CONFIG["TEMP_WAV_PATH"]) or os.path.getsize(CONFIG["TEMP_WAV_PATH"]) < 2000:
                BOT_STATE["status_msg"] = "Listening Active"
                continue

            BOT_STATE["status_msg"] = "Transcribing..."
            segments, info = model.transcribe(
                CONFIG["TEMP_WAV_PATH"],
                beam_size=5,
                language="en",
                condition_on_previous_text=False,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=400),
                initial_prompt=f"This is a conversation with a robot assistant named {CONFIG['BOT_NAME']}."
            )
            user_text = "".join([segment.text for segment in segments]).strip()

            if user_text and len(user_text) > 2:
                BOT_STATE["user_transcript"] = f"You: {user_text}"
                print(f"\n[Mic Capture]: {user_text}")

                if user_text.lower() in ["exit", "quit", "shutdown"]:
                    if os.path.exists(CONFIG["TEMP_WAV_PATH"]):
                        os.remove(CONFIG["TEMP_WAV_PATH"])
                    os._exit(0)

                query_robot_brain(user_text)
            else:
                BOT_STATE["status_msg"] = "Listening Active"
        except Exception as e:
            print(f"\n[LOOP FAULT]: {e}")
            time.sleep(0.1)


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


def get_high_res_eye_surface(emotion, side):
    """
    Draws a cute, detailed anime eye with EVE Wall-E vibes on a 160x140 transparent surface.
    side: -1 for left eye, 1 for right eye.
    """
    surf = pygame.Surface((160, 140), pygame.SRCALPHA)
    surf.fill((0, 0, 0, 0)) # transparent background

    # EVE glowing blue/cyan base color & white highlights
    eye_color = (0, 210, 255)
    white_color = (255, 255, 255)

    cx, cy = 80, 70

    # Base eye dimensions
    base_w = 90
    base_h = 100
    openness = 1.0
    brow_y_offset = 0
    brow_tilt = 0

    if emotion == "HAPPY":
        points = []
        for angle in range(210, 331, 5):
            rad = np.radians(angle)
            px = cx + 55 * np.cos(rad)
            py = cy + 15 + 35 * np.sin(rad)
            points.append((px, py))
        pygame.draw.lines(surf, eye_color, False, points, 14)

        lash_x = cx + side * 45
        lash_y = cy - 5
        pygame.draw.line(surf, eye_color, (lash_x, lash_y), (lash_x + side * 15, lash_y - 10), 8)

        brow_y = cy - 45
        pygame.draw.arc(surf, eye_color, (cx - 45, brow_y, 90, 30), 0.5, 2.6, 6)
        return surf

    elif emotion == "SAD":
        openness = 0.52
        brow_y_offset = 12
        brow_tilt = side * 15
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
        tilt_deg = 15 * side
    elif emotion == "THINKING":
        tilt_deg = -10 if side < 0 else 12

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
        r_rect.center = (cx, cy)
        surf.blit(rotated_iris, r_rect)

    pygame.draw.lines(surf, eye_color, False, rotated_lid, 8)

    brow_y = cy - base_h * 0.6 + brow_y_offset
    brow_half = base_w * 0.5
    brow_p1 = (cx - brow_half, brow_y + brow_tilt)
    brow_p2 = (cx + brow_half, brow_y - brow_tilt)
    rot_p1 = rotate_point(brow_p1, tilt_deg * 0.5, (cx, cy))
    rot_p2 = rotate_point(brow_p2, tilt_deg * 0.5, (cx, cy))
    pygame.draw.line(surf, eye_color, rot_p1, rot_p2, 6)

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


def draw_glowing_mouth(screen, cx, cy, emotion):
    color = (130, 240, 255)
    glow_color = (0, 80, 180)

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
    emotion = BOT_STATE["emotion"]

    left_eye_center = (250, 160)
    right_eye_center = (550, 160)
    mouth_center = (400, 255)

    left_eye_surf = get_high_res_eye_surface(emotion, side=-1)
    right_eye_surf = get_high_res_eye_surface(emotion, side=1)

    draw_led_grid(screen, left_eye_surf, left_eye_center[0], left_eye_center[1], grid_spacing=4)
    draw_led_grid(screen, right_eye_surf, right_eye_center[0], right_eye_center[1], grid_spacing=4)

    draw_glowing_mouth(screen, mouth_center[0], mouth_center[1], emotion)

    # Bottom UI dashboard
    pygame.draw.rect(screen, (16, 20, 35), (0, 370, 800, 110))
    pygame.draw.line(screen, (35, 42, 68), (0, 370), (800, 370), 2)

    accent_color = (0, 210, 255) if emotion != "SAD" else (255, 60, 100)
    if emotion == "THINKING":
        accent_color = (255, 200, 0)

    label_status = FONT_UI.render(f"SYSTEM STATUS : {BOT_STATE['status_msg']}", True, (0, 255, 150))
    label_input  = FONT_UI.render(f"MIC TRACK     : {BOT_STATE['user_transcript'][:70]}", True, (170, 180, 210))
    label_output = FONT_UI.render(f"ROBO REPLIES  : {BOT_STATE['bot_response'][:70]}", True, accent_color)
    label_config = FONT_UI.render(f"BACKEND={brain.CONFIG['BACKEND'].upper()} | BOT={CONFIG['BOT_NAME']}", True, (90, 105, 140))

    screen.blit(label_status, (20, 382))
    screen.blit(label_input,  (20, 405))
    screen.blit(label_output, (20, 428))
    screen.blit(label_config, (20, 453))

    pygame.display.flip()


def main():
    threading.Thread(target=voice_assistant_worker, daemon=True).start()
    while True:
        draw_interface()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()
        clock.tick(30)


if __name__ == "__main__":
    main()
