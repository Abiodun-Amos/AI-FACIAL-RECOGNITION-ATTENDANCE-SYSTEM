"""
Attendance Engine — Phase 3B (session-aware)
=============================================
Adds on top of Phase 3A:
  • Hall-based session lookup (only sessions for this device's hall)
  • PRESENT / LATE status based on grace_minutes
  • Cancellation enforcement (no logging on cancelled dates)
  • Level validation (wrong-level students are NOT logged)
  • Per-session duplicate prevention (one log per user per session per date)

Press 'q' to quit.

Usage:
    python -m src.attendance_engine
"""

import cv2
import sys
import time
from datetime import datetime

from src import config, database
from src.face_tracker import FaceTracker
from src.session_manager import get_active_session, describe_session
from src.face_utils import preprocess_face


class SessionState:
    """In-memory state for one run of the engine."""
    def __init__(self):
        self.logged_users      = {}   # (user_id, session_id) -> True
        self.logged_tracks     = set()
        self.recent_intruder_t = 0
        self.intruder_cooldown = 10
        self.count_present  = 0
        self.count_late     = 0
        self.count_intruder = 0
        self.count_wrong_level = 0


def load_recognizer():
    if not config.TRAINER_PATH.exists():
        print(f"[ERROR] No trained model at {config.TRAINER_PATH}")
        print("        Run: python -m src.train_model")
        sys.exit(1)
    rec = cv2.face.LBPHFaceRecognizer_create()
    rec.read(str(config.TRAINER_PATH))
    return rec


def build_user_lookup():
    return {u["user_id"]: u for u in database.get_all_users()}


def save_intruder_snapshot(frame, bbox, confidence):
    x, y, w, h = bbox
    pad_x = int(w * 0.3); pad_y = int(h * 0.3)
    x0 = max(0, x - pad_x)
    y0 = max(0, y - pad_y)
    x1 = min(frame.shape[1], x + w + pad_x)
    y1 = min(frame.shape[0], y + h + pad_y)
    snapshot = frame[y0:y1, x0:x1]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    filename = f"intruder_{ts}.jpg"
    path = config.INTRUDERS_DIR / filename
    cv2.imwrite(str(path), snapshot)
    return str(path)


def main():
    print("\n" + "=" * 60)
    print("  ATTENDANCE ENGINE — Phase 3B (session-aware)")
    print("=" * 60)

    database.init_db()
    hall = database.get_hall_by_name(config.CURRENT_HALL_NAME)
    if hall is None:
        print(f"[ERROR] Hall '{config.CURRENT_HALL_NAME}' not in DB.")
        print("        Run: python -m src.migrate_schema")
        sys.exit(1)

    hall_id = hall["hall_id"]
    print(f"[OK] Operating in hall: {config.CURRENT_HALL_NAME} (id={hall_id})")

    recognizer = load_recognizer()
    users      = build_user_lookup()
    tracker    = FaceTracker()
    state      = SessionState()

    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )

    cap = cv2.VideoCapture(config.CAMERA_INDEX, cv2.CAP_DSHOW)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  config.FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.FRAME_HEIGHT)
    if not cap.isOpened():
        print("[ERROR] Cannot open camera.")
        sys.exit(1)

    print(f"[OK] {len(users)} enrolled user(s) loaded.")
    print("[INFO] Press 'q' to stop.\n")

    prev_t = time.time()
    last_session_check = 0
    active_session = None    # refreshed every 5 seconds

    while True:
        ret, frame = cap.read()
        if not ret: continue

        now_t = time.time()

        # Refresh session status periodically (no need every frame)
        if now_t - last_session_check > 5:
            active_session = get_active_session(hall_id)
            last_session_check = now_t

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(
            gray,
            scaleFactor=config.HAAR_SCALE_FACTOR,
            minNeighbors=config.HAAR_MIN_NEIGHBORS,
            minSize=config.HAAR_MIN_SIZE,
        )

        # LBPH predict per detected face
        detections = []
        for (x, y, w, h) in faces:
            face_crop = preprocess_face(gray, (x, y, w, h))
            user_id, confidence = recognizer.predict(face_crop)
            detections.append(((x, y, w, h), (user_id, confidence)))

        tracks = tracker.update(detections)

        # ── Persistence + drawing per track ─────────────────
        for track in tracks:
            x, y, w, h = track.bbox
            smoothed = track.smoothed_prediction()

            if smoothed is None:
                color = (255, 255, 0)
                cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
                cv2.putText(frame, f"Analysing... ({len(track.history)}/4)",
                            (x, y - 8), cv2.FONT_HERSHEY_SIMPLEX,
                            0.55, color, 2)
                continue

            user_id, avg_conf = smoothed

            if avg_conf < config.CONFIDENCE_THRESHOLD:
                # ── RECOGNIZED ────────────────────────────────
                user = users.get(user_id)

                if user is None:
                    # Trainer label has no matching DB user (stale model).
                    # Treat as unknown to be safe.
                    color = (0, 0, 255)
                    status_txt = "UNKNOWN (stale model)"
                    label = f"id={user_id}  ({avg_conf:.1f})"
                    cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
                    cv2.rectangle(frame, (x, y - 28), (x + w, y), color, -1)
                    cv2.putText(frame, label, (x + 4, y - 8),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 1)
                    cv2.putText(frame, status_txt, (x, y + h + 22),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)
                    continue

                name = user["name"]
                color = (0, 255, 0)

                if active_session is None:
                    status_txt = "NO ACTIVE SESSION"
                elif user["user_level"] != active_session["course_level"]:
                    # Wrong-level student — do not log
                    status_txt = f"WRONG LEVEL (L{user['user_level']})"
                    color = (0, 165, 255)  # orange
                    key = (user_id, "wrong-level-warn")
                    if key not in state.logged_users:
                        state.logged_users[key] = True
                        state.count_wrong_level += 1
                        print(f"[WARN] {datetime.now().strftime('%H:%M:%S')} "
                              f"WRONG-LEVEL → {name} (L{user['user_level']}) "
                              f"in {active_session['course_code']} "
                              f"(L{active_session['course_level']})")
                else:
                    # Correct level — log if not already logged for this session
                    sid   = active_session["session_id"]
                    sdate = active_session["session_date"]
                    sstatus = active_session["status"]   # PRESENT or LATE
                    key = (user_id, sid)

                    if (key not in state.logged_users
                            and not database.has_attended_session(user_id, sid, sdate)):
                        database.log_attendance(
                            user_id=user_id,
                            confidence=avg_conf,
                            session_id=sid,
                            session_date=sdate,
                            course_id=active_session["course_id"],
                            hall_id=hall_id,
                            status=sstatus,
                        )
                        state.logged_users[key] = True
                        if sstatus == "PRESENT":
                            state.count_present += 1
                        else:
                            state.count_late += 1
                        print(f"[LOG] {datetime.now().strftime('%H:%M:%S')} "
                              f"{sstatus:<7} → {name} "
                              f"({active_session['course_code']}, "
                              f"conf {avg_conf:.1f})")
                        status_txt = sstatus
                    else:
                        status_txt = f"{sstatus} ✓"

                label = f"{name}  ({avg_conf:.1f})"
            else:
                # ── INTRUDER ──────────────────────────────────
                color = (0, 0, 255)
                status_txt = "INTRUDER"
                label = f"UNKNOWN  ({avg_conf:.1f})"

                cooled = (now_t - state.recent_intruder_t) > state.intruder_cooldown
                if track.track_id not in state.logged_tracks and cooled:
                    snap_path = save_intruder_snapshot(frame, track.bbox, avg_conf)
                    sid = active_session["session_id"] if active_session else None
                    sdate = active_session["session_date"] if active_session else None
                    database.log_intruder(
                        image_path=snap_path,
                        confidence=avg_conf,
                        session_id=sid,
                        session_date=sdate,
                        hall_id=hall_id,
                    )
                    state.logged_tracks.add(track.track_id)
                    state.recent_intruder_t = now_t
                    state.count_intruder += 1
                    print(f"[ALERT] {datetime.now().strftime('%H:%M:%S')} "
                          f"INTRUDER → {snap_path} (conf {avg_conf:.1f})")

            cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
            cv2.rectangle(frame, (x, y - 28), (x + w, y), color, -1)
            cv2.putText(frame, label, (x + 4, y - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 1)
            cv2.putText(frame, status_txt, (x, y + h + 22),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)

        # ── HUD ─────────────────────────────────────────────
        fps = 1.0 / (now_t - prev_t) if now_t != prev_t else 0
        prev_t = now_t

        sess_line = describe_session(active_session)
        sess_color = (0, 255, 0) if active_session else (100, 100, 100)

        cv2.rectangle(frame, (0, 0), (frame.shape[1], 55), (0, 0, 0), -1)
        cv2.putText(frame, sess_line, (10, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, sess_color, 2)
        cv2.putText(frame,
                    f"FPS:{fps:.1f}  Tracks:{len(tracks)}  "
                    f"P:{state.count_present}  L:{state.count_late}  "
                    f"I:{state.count_intruder}  WL:{state.count_wrong_level}",
                    (10, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        cv2.putText(frame, "Press 'q' to stop", (10, frame.shape[0] - 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        cv2.imshow("Attendance Engine - Phase 3B", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

    print("\n" + "=" * 60)
    print("  SESSION ENDED")
    print(f"  PRESENT   : {state.count_present}")
    print(f"  LATE      : {state.count_late}")
    print(f"  INTRUDERS : {state.count_intruder}")
    print(f"  WRONG-LVL : {state.count_wrong_level}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()