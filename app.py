
from flask import Flask, render_template, request, redirect, session, jsonify
import os, uuid, cv2, json, numpy as np
from paddleocr import PaddleOCR
from google.cloud import vision

app = Flask(__name__)
app.secret_key = "secret"

ocr = PaddleOCR(use_angle_cls=True, lang='ch')
vision_client = vision.ImageAnnotatorClient()

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

inventory = []
warehouse = {}

# ===== 影像強化（90%穩定版）=====
def crop_board(path):
    img = cv2.imread(path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    contours,_ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if contours:
        c = max(contours, key=cv2.contourArea)
        x,y,w,h = cv2.boundingRect(c)
        img = img[y:y+h, x:x+w]
        cv2.imwrite(path, img)

def auto_rotate(path):
    img = cv2.imread(path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    coords = np.column_stack(np.where(gray > 0))
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle
    (h,w)=img.shape[:2]
    M = cv2.getRotationMatrix2D((w//2,h//2), angle,1)
    img = cv2.warpAffine(img,M,(w,h))
    cv2.imwrite(path,img)

def extract_blue(path):
    img = cv2.imread(path)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    lower = np.array([100,50,50])
    upper = np.array([140,255,255])
    mask = cv2.inRange(hsv, lower, upper)
    img = cv2.bitwise_and(img,img,mask=mask)
    cv2.imwrite(path,img)

def denoise(path):
    img = cv2.imread(path)
    img = cv2.medianBlur(img,3)
    cv2.imwrite(path,img)

def enhance(path):
    img = cv2.imread(path)
    img = cv2.convertScaleAbs(img, alpha=1.5, beta=-30)
    kernel = np.array([[0,-1,0],[-1,5,-1],[0,-1,0]])
    img = cv2.filter2D(img,-1,kernel)
    cv2.imwrite(path,img)

def binarize(path):
    img = cv2.imread(path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    img = cv2.adaptiveThreshold(gray,255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,11,2)
    cv2.imwrite(path,img)

# ===== OCR =====
def run_ocr(path):
    text=""
    conf=0
    try:
        res = ocr.ocr(path)
        total=0;count=0
        for line in res:
            for w in line:
                text+=w[1][0]
                total+=w[1][1]
                count+=1
        if count>0:
            conf=round(total/count,2)
    except:
        pass

    if len(text.strip())<3:
        try:
            with open(path,"rb") as f:
                content=f.read()
            image = vision.Image(content=content)
            response = vision_client.text_detection(image=image)
            if response.text_annotations:
                text=response.text_annotations[0].description
                conf=0.9
        except:
            pass
    return text,conf

@app.route("/")
def home():
    return render_template("index.html", data=inventory)

@app.route("/upload", methods=["POST"])
def upload():
    file = request.files["image"]
    path = os.path.join(UPLOAD_FOLDER,file.filename)
    file.save(path)

    # 最終流程
    crop_board(path)
    auto_rotate(path)
    extract_blue(path)
    denoise(path)
    enhance(path)
    binarize(path)

    text,conf = run_ocr(path)
    return jsonify({"text":text,"confidence":conf})

@app.route("/add", methods=["POST"])
def add():
    t = request.form["text"]
    inventory.append(t)
    return redirect("/")

app.run(host="0.0.0.0", port=5000)
