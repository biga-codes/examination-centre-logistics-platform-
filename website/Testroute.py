import cv2
import numpy as np

def preprocess_webcam_image(image_bytes):
    #  bytes to numpy array for OpenCV
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    # Sharpning & MOTION BLURR
    kernel = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])
    img = cv2.filter2D(img, -1, kernel)

    # brightness Correction (AlphaContrast, BetaBrightness)
    img = cv2.convertScaleAbs(img, alpha=1.2, beta=10)

    # Convert back to bytes
    _, buffer = cv2.imencode('.jpg', img)
    return buffer.tobytes()