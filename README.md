# 🚀 VisionAI – YOLO11 Real-Time Object Detection & Video Surveillance

VisionAI is an AI-powered computer vision platform designed for intelligent object detection, real-time video analysis, and IP camera surveillance.

Built using **Python, Flask, Ultralytics YOLO11, OpenCV, and ByteTrack**, the platform enables users to detect, classify, and track objects in uploaded images, videos, and supported live camera streams.

## ✨ Key Features

- **Image Detection:** Upload images and detect multiple objects with bounding boxes, labels, and confidence scores.
- **Video Detection:** Process uploaded videos and generate annotated output videos.
- **Real-Time Object Detection:** Perform AI-powered detection on live video streams.
- **IP Camera Integration:** Connect compatible IP cameras through RTSP streams.
- **Object Tracking:** Track detected objects using ByteTrack.
- **Detection Analytics:** View detected classes, confidence scores, and object statistics.
- **CSV Reports:** Export detection information for further analysis.
- **Modern Web Interface:** Access AI detection features through a Flask-based dashboard.
- **Deployment Ready:** Docker configuration and Hugging Face Spaces deployment preparation.

## 🧠 Technology Stack

| Category | Technologies |
|---|---|
| Programming | Python |
| Backend | Flask |
| Object Detection | Ultralytics YOLO11 |
| Computer Vision | OpenCV |
| Object Tracking | ByteTrack |
| Frontend | HTML, CSS, JavaScript |
| Video Processing | OpenCV |
| Production Server | Gunicorn |
| Containerization | Docker |
| Deployment | Hugging Face Spaces |

## 🏗️ System Architecture

1. User uploads an image or video, or connects a supported IP camera.
2. Flask receives the input and manages the processing request.
3. YOLO11 performs object detection.
4. ByteTrack associates detected objects across video frames.
5. OpenCV processes frames and generates annotated visual outputs.
6. The dashboard displays detection results and analytics.

## 📸 Supported Detection Modes

- Image-based object detection
- Uploaded video detection
- Live video stream detection
- RTSP-based IP camera detection
- Multi-object tracking

## ⚙️ Installation

Clone the repository:

```bash
git clone https://github.com/YOUR_USERNAME/YOUR_REPOSITORY.git
cd YOUR_REPOSITORY
```

Create a virtual environment:

```bash
python -m venv .venv
```

Activate on Windows:

```powershell
.venv\Scripts\Activate.ps1
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the application:

```bash
python app.py
```

Open:

```text
http://127.0.0.1:5000
```

## 📹 IP Camera Configuration

Connect a compatible IP camera using an RTSP stream URL.

Example:

```text
rtsp://username:password@CAMERA_IP:554/stream1
```

Actual RTSP paths depend on the camera manufacturer and configuration.

**Note:** Live camera access requires network connectivity between the application server and the camera.

## 🚀 Deployment

VisionAI includes deployment preparation for Docker-based environments and Hugging Face Spaces.

For Hugging Face deployment:

1. Create a new Hugging Face Space.
2. Select Docker as the SDK.
3. Upload the project files.
4. Configure the required environment variables.
5. Build and launch the application.

For remote IP camera access, configure a secure VPN or edge relay.

## 🔮 Future Improvements

- Multi-camera management dashboard
- Real-time intrusion and restricted-area alerts
- Email notifications for security events
- Detection history and searchable event logs
- Advanced analytics and reporting
- GPU-accelerated inference
- User roles and access management
- Scalable camera streaming architecture

## 👨‍💻 Developer

Developed as an AI and Computer Vision project focused on intelligent surveillance, real-time object detection, and practical AI deployment.

**Core Technologies:** Python | Flask | YOLO11 | OpenCV | ByteTrack | Computer Vision | Deep Learning

## 📄 License

Choose and add an appropriate open-source license before distributing the project. Check the licenses of all included models and dependencies.
