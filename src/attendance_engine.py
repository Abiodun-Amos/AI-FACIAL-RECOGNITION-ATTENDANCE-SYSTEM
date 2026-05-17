"""
Attendance Engine — Phase 3B (backend-agnostic)
================================================
Runs on EITHER recognition backend via config.RECOGNITION_BACKEND.
All Phase 3B logic (sessions, PRESENT/LATE, cancellations, level
validation, intruders, duplicate prevention) is unchanged — only
the recognition call is now abstracted behind the backend adapter.

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
from src.session_manager import get_active_session, get_scheduled_session, describe_session
from src.recognizer_backend import get_backend, bbox_of
from src.liveness import LivenessChecker


class SessionState:
    def __init__(self):
        self.logged_users      = {}
        self.logged_tracks     = set()
        self.recent_intruder_t = 0
        self.intruder_cooldown = 10
        self.count_present  = 0
        self.count_late     = 0
        self.count_intruder = 0
        self.count_wrong_level = 0


def build_user_lookup():
    return {u["user_id"]: u for u in database.get_all_users()}


def save_intruder_snapshot(frame, bbox, score):
    x, y, w, h = bbox
    pad_x = int(w * 0.3); pad_y = int(h * 0.3)
    x0 = max(0, x - pad_x); y0 = max(0, y - pad_y)
    x1 = min(frame.shape[1], x + w + pad_x)
    y1 = min(frame.shape[0], y + h + pad_y)
    snap = frame[y0:y1, x0:x1]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    path = config.INTRUDERS_DIR / f"intruder_{ts}.jpg"
    cv2.imwrite(str(path), snap)
    return str(path)


def is_recognized(backend, score):
    """Direction-aware acceptance check."""
    if backend.kind == "LBPH_DISTANCE":
        return score < backend.threshold      # lower = better
    return score >= backend.threshold         # DNN: higher = better


def main():
    print("\n" + "=" * 60)
    print(f"  ATTENDANCE ENGINE — backend: {config.RECOGNITION_BACKEND}")
    print("=" * 60)

    database.init_db()
    hall = database.get_hall_by_name(config.CURRENT_HALL_NAME)
    if hall is None:
        print(f"[ERROR] Hall '{config.CURRENT_HALL_NAME}' not in DB.")
        sys.exit(1)
    hall_id = hall["hall_id"]
    print(f"[OK] Hall: {config.CURRENT_HALL_NAME} (id={hall_id})")

    backend = get_backend()
    users   = build_user_lookup()
    tracker = FaceTracker()
    state   = SessionState()

    cap = cv2.VideoCapture(config.CAMERA_INDEX, cv2.CAP_DSHOW)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  config.FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.FRAME_HEIGHT)
    if not cap.isOpened():
        print("[ERROR] Cannot open camera.")
        sys.exit(1)

    print(f"[OK] {len(users)} enrolled user(s). Press 'q' to stop.\n")

    prev_t = time.time()
    last_session_check = 0
    active_session = None
    scheduled_session = None

    while True:
        ret, frame = cap.read()
        if not ret:
            continue
        now_t = time.time()

        if now_t - last_session_check > 5:
            active_session = get_active_session(hall_id)        # cancellation-aware → attendance
            scheduled_session = get_scheduled_session(hall_id)  # window-only → intruder logging
            last_session_check = now_t

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Backend-specific detection (Haar for LBPH, YuNet for DNN)
        faces = backend.detect(frame, gray)

        detections = []
        for face in faces:
            uid, score, kind = backend.identify(frame, gray, face)
            bbox = bbox_of(backend, face)
            # Pack for the tracker: use -1 sentinel for "unknown"
            packed_id = uid if uid is not None else -1
            detections.append((bbox, (packed_id, score)))

        tracks = tracker.update(detections)

        for track in tracks:
            # Attach a liveness checker to this track on first sight
            if config.LIVENESS_ENABLED:
                if not hasattr(track, "liveness"):
                    track.liveness = LivenessChecker()
                track.liveness.update(gray, track.bbox)
            x, y, w, h = track.bbox
            smoothed = track.smoothed_prediction()

            if smoothed is None:
                color = (255, 255, 0)
                cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
                cv2.putText(frame, f"Analysing... ({len(track.history)}/5)",
                            (x, y - 8), cv2.FONT_HERSHEY_SIMPLEX,
                            0.55, color, 2)
                continue

            voted_id, avg_score = smoothed

            if voted_id == -1:
                # ── INTRUDER ──
                color = (0, 0, 255)
                label = f"UNKNOWN ({avg_score:.3f})"

                # Intruder logging is gated on the SCHEDULED window
                # (cancellation-blind), NOT on active_session.
                # → logs during any timetabled slot, even if cancelled
                # → silent during true off-hours / breaks / unscheduled days
                if scheduled_session is not None:
                    status_txt = "INTRUDER"
                    cooled = (now_t - state.recent_intruder_t) > state.intruder_cooldown
                    if track.track_id not in state.logged_tracks and cooled:
                        snap = save_intruder_snapshot(frame, track.bbox, avg_score)
                        sid   = scheduled_session["session_id"]
                        sdate = scheduled_session["session_date"]
                        database.log_intruder(snap, avg_score, sid, sdate, hall_id)
                        state.logged_tracks.add(track.track_id)
                        state.recent_intruder_t = now_t
                        state.count_intruder += 1
                        print(f"[ALERT] {datetime.now():%H:%M:%S} INTRUDER "
                              f"→ {snap} (score {avg_score:.3f})")
                else:
                    # Outside any scheduled window — detected but NOT logged
                    status_txt = "UNKNOWN (off-hours, not logged)"
            else:
                user = users.get(voted_id)
                if user is None:
                    color = (0, 0, 255)
                    status_txt = "UNKNOWN (stale)"
                    label = f"id={voted_id} ({avg_score:.3f})"
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
                    status_txt = f"WRONG LEVEL (L{user['user_level']})"
                    color = (0, 165, 255)
                    key = (voted_id, "wl")
                    if key not in state.logged_users:
                        state.logged_users[key] = True
                        state.count_wrong_level += 1
                        print(f"[WARN] {datetime.now():%H:%M:%S} WRONG-LEVEL "
                              f"→ {name} (L{user['user_level']}) in "
                              f"{active_session['course_code']} "
                              f"(L{active_session['course_level']})")
                else:
                    sid     = active_session["session_id"]
                    sdate   = active_session["session_date"]
                    sstatus = active_session["status"]
                    key = (voted_id, sid)

                    already_logged = (
                        key in state.logged_users
                        or database.has_attended_session(voted_id, sid, sdate)
                    )

                    if already_logged:
                        status_txt = f"{sstatus} ✓"
                    else:
                        # ── Liveness gate (anti-spoofing) ──
                        if config.LIVENESS_ENABLED:
                            is_live, mscore = track.liveness.is_live()
                            print(f"[LIVENESS] track={track.track_id} "
                                  f"is_live={is_live} score={mscore}")
                            if is_live is None:
                                # Still sampling motion — don't log yet
                                color = (255, 255, 0)
                                status_txt = "Liveness check..."
                                label = f"{name} (checking)"
                                cv2.rectangle(frame, (x, y), (x + w, y + h),
                                              color, 2)
                                cv2.rectangle(frame, (x, y - 28), (x + w, y),
                                              color, -1)
                                cv2.putText(frame, label, (x + 4, y - 8),
                                            cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                                            (0, 0, 0), 1)
                                cv2.putText(frame, status_txt, (x, y + h + 22),
                                            cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                                            color, 2)
                                continue
                            if is_live is False:
                                # Static → likely photo spoof. Refuse.
                                color = (0, 0, 255)
                                status_txt = "SPOOF? (static)"
                                label = f"{name} STATIC ({mscore:.1f})"
                                cv2.rectangle(frame, (x, y), (x + w, y + h),
                                              color, 2)
                                cv2.rectangle(frame, (x, y - 28), (x + w, y),
                                              color, -1)
                                cv2.putText(frame, label, (x + 4, y - 8),
                                            cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                                            (0, 0, 0), 1)
                                cv2.putText(frame, status_txt, (x, y + h + 22),
                                            cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                                            color, 2)
                                continue
                            # is_live is True → fall through and log

                        # ── Passed all gates → log attendance ──
                        database.log_attendance(
                            user_id=voted_id, confidence=avg_score,
                            session_id=sid, session_date=sdate,
                            course_id=active_session["course_id"],
                            hall_id=hall_id, status=sstatus)
                        state.logged_users[key] = True
                        if sstatus == "PRESENT":
                            state.count_present += 1
                        else:
                            state.count_late += 1
                        print(f"[LOG] {datetime.now():%H:%M:%S} {sstatus:<7} "
                              f"→ {name} ({active_session['course_code']}, "
                              f"score {avg_score:.3f})")
                        status_txt = sstatus

                label = f"{name} ({avg_score:.3f})"

            cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
            cv2.rectangle(frame, (x, y - 28), (x + w, y), color, -1)
            cv2.putText(frame, label, (x + 4, y - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 1)
            cv2.putText(frame, status_txt, (x, y + h + 22),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)

        # HUD
        fps = 1.0 / (now_t - prev_t) if now_t != prev_t else 0
        prev_t = now_t
        sess_line = describe_session(active_session)
        if active_session:
            sess_color = (0, 255, 0)            # green: attendance live
        elif scheduled_session:
            sess_line = f"SCHEDULED (cancelled?) — intruder-logging ON"
            sess_color = (0, 165, 255)          # orange: window open, no attendance
        else:
            sess_color = (120, 120, 120)        # gray: fully off
        cv2.rectangle(frame, (0, 0), (frame.shape[1], 55), (0, 0, 0), -1)
        cv2.putText(frame, sess_line, (10, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, sess_color, 2)
        cv2.putText(frame,
                    f"[{backend.name}] FPS:{fps:.1f}  Tracks:{len(tracks)}  "
                    f"P:{state.count_present} L:{state.count_late} "
                    f"I:{state.count_intruder} WL:{state.count_wrong_level}",
                    (10, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        cv2.putText(frame, "Press 'q' to stop", (10, frame.shape[0] - 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        cv2.imshow(f"Attendance Engine [{backend.name}]", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    print("\n" + "=" * 60)
    print(f"  SESSION ENDED  (backend: {backend.name})")
    print(f"  PRESENT:{state.count_present}  LATE:{state.count_late}  "
          f"INTRUDER:{state.count_intruder}  WRONG-LVL:{state.count_wrong_level}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()