import os
import csv
import uuid
import threading
import time
import socket
import ipaddress
import hmac
import base64
from urllib.parse import urlsplit
from pathlib import Path
from datetime import datetime

import cv2
import torch
from flask import Flask, render_template, request, jsonify, send_from_directory, abort
from werkzeug.utils import secure_filename
from ultralytics import YOLO

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {"mp4", "avi", "mov", "mkv", "webm"}
MAX_UPLOAD_MB = 700

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024

jobs = {}
jobs_lock = threading.Lock()
model_cache = {}
model_lock = threading.Lock()

# One live camera per app process in this starter deployment. Use a dedicated
# stream worker/service for multi-camera, multi-user production workloads.
live_camera = None
live_camera_lock = threading.Lock()



class LiveCamera:
    """Background RTSP reader with an MJPEG frame buffer for the browser."""
    def __init__(self, source, model_name, confidence, image_size, tracking=True):
        self.source = source
        self.model_name = model_name
        self.confidence = confidence
        self.image_size = image_size
        self.tracking = tracking
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.frame = None
        self.status = "starting"
        self.message = "Connecting to camera..."
        self.total_detections = 0
        self.class_counts = {}
        self.thread = threading.Thread(target=self.run, daemon=True)

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread.is_alive():
            self.thread.join(timeout=4)

    def snapshot(self):
        with self.lock:
            return {
                "status": self.status,
                "message": self.message,
                "total_detections": self.total_detections,
                "class_counts": dict(self.class_counts),
            }

    def run(self):
        cap = None
        try:
            model = get_model(self.model_name)
            # FFmpeg-backed OpenCV builds can honor these RTSP transport options.
            os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")
            cap = cv2.VideoCapture(self.source, cv2.CAP_FFMPEG)
            if not cap.isOpened():
                cap.release()
                cap = cv2.VideoCapture(self.source)
            if not cap.isOpened():
                raise RuntimeError("Could not connect to the IP camera. Check its RTSP URL, credentials, network and stream path.")

            with self.lock:
                self.status = "running"
                self.message = "Live object detection is running."

            while not self.stop_event.is_set():
                ok, frame = cap.read()
                if not ok:
                    with self.lock:
                        self.status = "reconnecting"
                        self.message = "Camera frame unavailable; reconnecting..."
                    cap.release()
                    if self.stop_event.wait(2):
                        break
                    cap = cv2.VideoCapture(self.source, cv2.CAP_FFMPEG)
                    if not cap.isOpened():
                        continue
                    with self.lock:
                        self.status = "running"
                        self.message = "Camera reconnected."
                    continue

                if self.tracking:
                    result = model.track(source=frame, persist=True, tracker="bytetrack.yaml",
                                         conf=self.confidence, imgsz=self.image_size, verbose=False)[0]
                else:
                    result = model.predict(source=frame, conf=self.confidence,
                                            imgsz=self.image_size, verbose=False)[0]

                boxes = result.boxes
                if boxes is not None and len(boxes):
                    with self.lock:
                        self.total_detections += len(boxes)
                        for class_id in boxes.cls.tolist():
                            name = model.names[int(class_id)]
                            self.class_counts[name] = self.class_counts.get(name, 0) + 1

                annotated = result.plot()
                # Resize oversized camera frames to keep MJPEG bandwidth manageable.
                h, w = annotated.shape[:2]
                if w > 1280:
                    new_h = int(h * 1280 / w)
                    annotated = cv2.resize(annotated, (1280, new_h))
                encoded, buffer = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 82])
                if encoded:
                    with self.lock:
                        self.frame = buffer.tobytes()
        except Exception as exc:
            with self.lock:
                self.status = "failed"
                self.message = str(exc)
        finally:
            if cap is not None:
                cap.release()
            with self.lock:
                if self.status not in {"failed"}:
                    self.status = "stopped"
                    self.message = "Camera stream stopped."


def validate_private_camera_url(raw_url):
    """Allow RTSP URLs only when the hostname resolves to a private/local IP.

    This reduces SSRF exposure when the dashboard is deployed. Put the app on
    the same LAN/VPN as the camera; do not expose camera ports to the internet.
    """
    try:
        parsed = urlsplit(raw_url)
        if parsed.scheme not in {"rtsp", "rtsps"} or not parsed.hostname:
            return False
        if parsed.port and not (1 <= parsed.port <= 65535):
            return False
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 554, type=socket.SOCK_STREAM)
        return bool(addresses) and all(ipaddress.ip_address(item[4][0]).is_private for item in addresses)
    except (ValueError, OSError):
        return False


@app.before_request
def protect_deployed_instance():
    """Optional HTTP Basic Auth; mandatory when DEPLOYMENT_MODE=production."""
    if request.path == "/healthz":
        return None
    if os.environ.get("DEPLOYMENT_MODE", "development").lower() != "production":
        return None
    username = os.environ.get("VISIONAI_USERNAME", "")
    password = os.environ.get("VISIONAI_PASSWORD", "")
    if not username or not password:
        return jsonify(error="Deployment credentials are not configured."), 503
    header = request.headers.get("Authorization", "")
    try:
        scheme, token = header.split(" ", 1)
        supplied_user, supplied_password = base64.b64decode(token).decode("utf-8").split(":", 1)
    except Exception:
        scheme, supplied_user, supplied_password = "", "", ""
    valid = (scheme.lower() == "basic"
             and hmac.compare_digest(supplied_user, username)
             and hmac.compare_digest(supplied_password, password))
    if not valid:
        return jsonify(error="Authentication required."), 401, {"WWW-Authenticate": 'Basic realm="VisionAI"'}
    return None


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def get_model(model_name):
    # Cache loaded models so repeated jobs do not reload weights unnecessarily.
    with model_lock:
        if model_name not in model_cache:
            model_cache[model_name] = YOLO(f"{model_name}.pt")
        return model_cache[model_name]


def update_job(job_id, **kwargs):
    with jobs_lock:
        jobs[job_id].update(kwargs)


def process_video(job_id, input_path, model_name, confidence, image_size, tracking):
    output_path = OUTPUT_DIR / f"{job_id}_annotated.mp4"
    csv_path = OUTPUT_DIR / f"{job_id}_detections.csv"
    cap = None
    writer = None

    try:
        update_job(job_id, status="loading", message="Loading YOLO11 model...")
        model = get_model(model_name)

        cap = cv2.VideoCapture(str(input_path))
        if not cap.isOpened():
            raise RuntimeError("OpenCV could not open this video.")

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        if width <= 0 or height <= 0:
            raise RuntimeError("Could not read video dimensions.")

        # mp4v is broadly compatible with local OpenCV installations.
        writer = cv2.VideoWriter(
            str(output_path),
            cv2.VideoWriter_fourcc(*"mp4v"),
            fps,
            (width, height)
        )
        if not writer.isOpened():
            raise RuntimeError("Could not create output video. Check OpenCV/codec support.")

        update_job(
            job_id,
            status="processing",
            message="Detecting objects...",
            total_frames=total_frames,
            fps=round(fps, 2),
            width=width,
            height=height,
            device="CUDA: " + torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU"
        )

        frame_index = 0
        detection_count = 0
        class_counts = {}
        records = []

        while True:
            ok, frame = cap.read()
            if not ok:
                break

            if tracking:
                result = model.track(
                    source=frame,
                    persist=True,
                    tracker="bytetrack.yaml",
                    conf=confidence,
                    imgsz=image_size,
                    verbose=False
                )[0]
            else:
                result = model.predict(
                    source=frame,
                    conf=confidence,
                    imgsz=image_size,
                    verbose=False
                )[0]

            annotated = result.plot()

            if result.boxes is not None and len(result.boxes) > 0:
                boxes = result.boxes
                for i in range(len(boxes)):
                    class_id = int(boxes.cls[i].item())
                    class_name = model.names[class_id]
                    score = float(boxes.conf[i].item())
                    track_id = None

                    if tracking and boxes.id is not None:
                        track_id = int(boxes.id[i].item())

                    x1, y1, x2, y2 = boxes.xyxy[i].tolist()
                    detection_count += 1
                    class_counts[class_name] = class_counts.get(class_name, 0) + 1
                    records.append([
                        frame_index,
                        round(frame_index / fps, 3),
                        class_id,
                        class_name,
                        round(score, 4),
                        track_id,
                        round(x1, 2), round(y1, 2),
                        round(x2, 2), round(y2, 2)
                    ])

            writer.write(annotated)
            frame_index += 1

            if frame_index % 5 == 0 or frame_index == total_frames:
                progress = min(100, round(frame_index / total_frames * 100, 1)) if total_frames else 0
                update_job(
                    job_id,
                    progress=progress,
                    processed_frames=frame_index,
                    total_detections=detection_count,
                    class_counts=class_counts,
                    message=f"Processed {frame_index:,} frames"
                )

        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            csv_writer = csv.writer(f)
            csv_writer.writerow([
                "frame", "timestamp_seconds", "class_id", "class_name",
                "confidence", "track_id", "x1", "y1", "x2", "y2"
            ])
            csv_writer.writerows(records)

        if frame_index == 0:
            raise RuntimeError("No frames were decoded from this video.")

        update_job(
            job_id,
            status="completed",
            progress=100,
            processed_frames=frame_index,
            total_detections=detection_count,
            class_counts=class_counts,
            video_url=f"/download/{job_id}/video",
            csv_url=f"/download/{job_id}/csv",
            message="Detection completed successfully."
        )

    except Exception as exc:
        update_job(job_id, status="failed", message=str(exc))
    finally:
        if cap is not None:
            cap.release()
        if writer is not None:
            writer.release()
        # Keep uploaded videos for possible reprocessing; remove manually if desired.


@app.route("/healthz")
def healthz():
    return jsonify(status="ok")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/upload", methods=["POST"])
def upload_video():
    if "video" not in request.files:
        return jsonify(error="Please choose a video file."), 400

    file = request.files["video"]
    if not file.filename:
        return jsonify(error="No file selected."), 400
    if not allowed_file(file.filename):
        return jsonify(error="Unsupported format. Use MP4, AVI, MOV, MKV, or WEBM."), 400

    model_name = request.form.get("model", "yolo11n")
    if model_name not in {"yolo11n", "yolo11s", "yolo11m", "yolo11l", "yolo11x"}:
        return jsonify(error="Invalid model selection."), 400

    try:
        confidence = float(request.form.get("confidence", 0.30))
        image_size = int(request.form.get("image_size", 640))
    except ValueError:
        return jsonify(error="Invalid confidence or image size."), 400

    if not 0.05 <= confidence <= 0.95:
        return jsonify(error="Confidence must be between 0.05 and 0.95."), 400
    if image_size not in {320, 480, 640, 800, 960, 1280}:
        return jsonify(error="Unsupported image size."), 400

    job_id = uuid.uuid4().hex[:12]
    original_name = secure_filename(file.filename)
    input_path = UPLOAD_DIR / f"{job_id}_{original_name}"
    file.save(input_path)

    tracking = request.form.get("tracking", "true").lower() == "true"

    with jobs_lock:
        jobs[job_id] = {
            "id": job_id,
            "filename": original_name,
            "status": "queued",
            "progress": 0,
            "processed_frames": 0,
            "total_frames": 0,
            "total_detections": 0,
            "class_counts": {},
            "message": "Video uploaded. Job queued.",
            "created_at": datetime.now().isoformat(timespec="seconds")
        }

    thread = threading.Thread(
        target=process_video,
        args=(job_id, str(input_path), model_name, confidence, image_size, tracking),
        daemon=True
    )
    thread.start()
    return jsonify(job_id=job_id, message="Upload successful. Detection started.")


@app.route("/api/status/<job_id>")
def job_status(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            return jsonify(error="Job not found."), 404
        return jsonify(job.copy())


@app.route("/api/camera/start", methods=["POST"])
def start_camera():
    global live_camera
    data = request.get_json(silent=True) or {}
    camera_url = (data.get("camera_url") or "").strip()
    model_name = data.get("model", "yolo11n")
    if model_name not in {"yolo11n", "yolo11s", "yolo11m", "yolo11l", "yolo11x"}:
        return jsonify(error="Invalid model selection."), 400
    try:
        confidence = float(data.get("confidence", 0.30))
        image_size = int(data.get("image_size", 640))
    except (TypeError, ValueError):
        return jsonify(error="Invalid confidence or image size."), 400
    if not 0.05 <= confidence <= 0.95 or image_size not in {320, 480, 640, 800, 960, 1280}:
        return jsonify(error="Confidence or image size is outside the supported range."), 400
    if not validate_private_camera_url(camera_url):
        return jsonify(error="Enter a valid RTSP/RTSPS URL for a camera on a private LAN or VPN."), 400

    with live_camera_lock:
        if live_camera and live_camera.thread.is_alive():
            return jsonify(error="A live camera is already running. Stop it before starting another."), 409
        live_camera = LiveCamera(camera_url, model_name, confidence, image_size,
                                 bool(data.get("tracking", True)))
        live_camera.start()
    return jsonify(message="Camera connection started.", feed_url="/camera/live.mjpg")


@app.route("/api/camera/status")
def camera_status():
    with live_camera_lock:
        camera = live_camera
    if not camera:
        return jsonify(status="stopped", message="No camera session is active.", total_detections=0, class_counts={})
    return jsonify(camera.snapshot())


@app.route("/api/camera/stop", methods=["POST"])
def stop_camera():
    global live_camera
    with live_camera_lock:
        camera = live_camera
        live_camera = None
    if camera:
        camera.stop()
    return jsonify(message="Camera stop requested.")


@app.route("/camera/live.mjpg")
def camera_feed():
    def generate():
        while True:
            with live_camera_lock:
                camera = live_camera
            if not camera:
                break
            with camera.lock:
                frame = camera.frame
                status = camera.status
            if frame:
                yield (b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                       + str(len(frame)).encode() + b"\r\n\r\n" + frame + b"\r\n")
            elif status in {"failed", "stopped"}:
                break
            time.sleep(0.04)
    return app.response_class(generate(), mimetype="multipart/x-mixed-replace; boundary=frame",
                              headers={"Cache-Control": "no-store, no-cache, must-revalidate"})


@app.route("/download/<job_id>/<kind>")
def download_result(job_id, kind):
    if kind == "video":
        path = OUTPUT_DIR / f"{job_id}_annotated.mp4"
        download_name = f"yolo11_{job_id}_annotated.mp4"
    elif kind == "csv":
        path = OUTPUT_DIR / f"{job_id}_detections.csv"
        download_name = f"yolo11_{job_id}_detections.csv"
    else:
        abort(404)

    if not path.exists():
        abort(404)
    return send_from_directory(path.parent, path.name, as_attachment=True, download_name=download_name)


@app.errorhandler(413)
def too_large(_):
    return jsonify(error=f"File is too large. Maximum upload size is {MAX_UPLOAD_MB} MB."), 413


if __name__ == "__main__":
    print("YOLO11 Video Detection running at http://127.0.0.1:5000")
    print("GPU available:", torch.cuda.is_available())
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False, threaded=True)
