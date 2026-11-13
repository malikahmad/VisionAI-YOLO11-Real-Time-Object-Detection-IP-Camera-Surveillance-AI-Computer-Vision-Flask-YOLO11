# VisionAI deployment and live IP camera guide

## 1. Run locally on the camera network (recommended for RTSP)

The computer running VisionAI must be able to reach the camera over the LAN or a VPN. Enable RTSP in the camera/NVR settings and create a dedicated read-only camera account. Typical URL shape:

`rtsp://USERNAME:PASSWORD@192.168.1.50:554/STREAM_PATH`

The exact stream path is camera-vendor-specific. Do not paste credentials into public tickets, screenshots, source control, or chat. The app accepts RTSP/RTSPS URLs that resolve to private/local IP addresses as a basic SSRF safeguard.

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
$env:DEPLOYMENT_MODE = "development"
python app.py
```

Open `http://127.0.0.1:5000`, enter the RTSP URL in the IP camera panel, and start live detection. Select YOLO11n for lower latency; larger models may improve accuracy but need more compute. Only one camera stream is supported by this starter implementation.

## 2. Docker deployment on a LAN-connected server or VPN-connected VPS

This is the recommended deployment path when live camera access is required. The Docker host must have a network route to the camera subnet. Do not port-forward camera RTSP ports to the public internet.

```bash
docker build -t visionai:latest .
docker run --name visionai --restart unless-stopped \
  -p 5000:5000 \
  -e DEPLOYMENT_MODE=production \
  -e VISIONAI_USERNAME='replace-with-user' \
  -e VISIONAI_PASSWORD='replace-with-a-long-random-password' \
  -v visionai-uploads:/app/uploads \
  -v visionai-outputs:/app/outputs \
  visionai:latest
```

Open `http://SERVER-IP:5000` behind a trusted LAN or reverse proxy with HTTPS. HTTP Basic Authentication is enabled when `DEPLOYMENT_MODE=production`. Use HTTPS (for example, through Caddy or Nginx with TLS) so credentials are not sent in clear text.

## 3. Render / other cloud platforms

The included `render.yaml`, `Dockerfile`, and `Procfile` provide a cloud deployment starting point. Configure `VISIONAI_USERNAME` and `VISIONAI_PASSWORD` as secret environment variables in the hosting dashboard. The cloud service can process uploaded videos, but a camera at a home/office behind a private router is normally unreachable from a public cloud host. For live camera detection, establish a private VPN route from the cloud host to the camera network, or run the VisionAI Docker container on a machine inside that network. The app intentionally rejects RTSP hosts that do not resolve to private/local addresses.

Free or ephemeral hosting may sleep, restart, or erase local files. Use persistent storage for uploads/results if you need them to survive restarts. GPU acceleration is not assumed by this deployment template; CPU inference may be slow, especially with YOLO11m/l/x.

## 4. Production limitations to address before scaling

- One live camera per application process; one worker is configured because stream state is held in memory.
- Camera sessions and upload-job state are in memory and are lost on restart.
- For multiple cameras/users, move stream workers to a dedicated service and use Redis plus Celery/RQ for jobs and shared status.
- Add a proper user/role system, audit logging, rate limiting, retention policies, and HTTPS reverse proxy before exposing to a broad audience.
- YOLO11 pretrained COCO weights recognize the supported COCO classes; they do not identify every possible object.
- Detection counts are frame-level observations, not unique people/object counts. ByteTrack IDs are temporary tracking IDs, not identities.
