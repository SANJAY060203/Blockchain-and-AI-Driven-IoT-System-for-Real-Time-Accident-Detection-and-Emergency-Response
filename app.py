import base64
import os
import uuid
import mimetypes
import math
import requests
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from inference_sdk import InferenceHTTPClient

# Google API libraries for Gmail OAuth2
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Email MIME libraries
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

# Import our blockchain from blockchain_module.py
from blockchain_module import Blockchain
os.environ["PENDRIVE_PATH"] = r"C:\Users\Sanjay\OneDrive\Desktop\emergency response system\EDGE"

app = Flask(__name__)

SCOPES = ['https://www.googleapis.com/auth/gmail.send']

def get_gmail_service():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    service = build('gmail', 'v1', credentials=creds)
    return service

def create_message(sender, to, subject, message_text):
    msg = MIMEText(message_text, 'html')
    msg['to'] = to
    msg['from'] = sender
    msg['subject'] = subject
    raw_message = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    return {'raw': raw_message}

def create_message_with_attachment(sender, to, subject, message_text, file_path):
    message = MIMEMultipart()
    message['to'] = to
    message['from'] = sender
    message['subject'] = subject
    msg_text = MIMEText(message_text, 'html')
    message.attach(msg_text)
    content_type, encoding = mimetypes.guess_type(file_path)
    if content_type is None or encoding is not None:
        content_type = 'application/octet-stream'
    main_type, sub_type = content_type.split('/', 1)
    with open(file_path, 'rb') as f:
        msg_attachment = MIMEBase(main_type, sub_type)
        msg_attachment.set_payload(f.read())
    encoders.encode_base64(msg_attachment)
    filename = os.path.basename(file_path)
    msg_attachment.add_header('Content-Disposition', 'attachment', filename=filename)
    message.attach(msg_attachment)
    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
    return {'raw': raw_message}

CONTROL_CENTER = (9.0, 77.5)

def get_distance(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def query_nearby_facilities(lat, lon, radius=20000):
    query = f"""
      [out:json];
      (
        node["amenity"="hospital"](around:{radius},{lat},{lon});
        node["amenity"="police"](around:{radius},{lat},{lon});
        node["emergency"="fire_station"](around:{radius},{lat},{lon});
      );
      out;
    """
    url = "https://overpass-api.de/api/interpreter?data=" + requests.utils.quote(query)
    nearest = {"hospital": None, "police": None, "fire_station": None}
    try:
        response = requests.get(url)
        data = response.json()
        for element in data.get("elements", []):
            if "tags" not in element:
                continue
            category = element["tags"].get("amenity") or element["tags"].get("emergency")
            if category not in nearest:
                continue
            d = get_distance(lat, lon, element["lat"], element["lon"])
            if nearest[category] is None or d < nearest[category]["distance"]:
                nearest[category] = {
                    "lat": element["lat"],
                    "lon": element["lon"],
                    "name": element["tags"].get("name", f"Unnamed {category}"),
                    "distance": d
                }
    except Exception as e:
        print("Error querying nearby facilities:", e)
    return nearest

def send_emergency_email(accident_type, details, attachment_path=None):
    accident_lat, accident_lon = details.get("location", (None, None))
    facilities = query_nearby_facilities(accident_lat, accident_lon, radius=20000)
    details["nearest_facilities"] = facilities

    hospital_info = facilities.get("hospital")
    police_info = facilities.get("police")
    fire_info = facilities.get("fire_station")

    facility_text = ""
    if hospital_info:
        facility_text += f"<p>Nearest Hospital: {hospital_info['name']} ({hospital_info['distance']:.0f} m) at {hospital_info['lat']}, {hospital_info['lon']}</p>"
    if police_info:
        facility_text += f"<p>Nearest Police Station: {police_info['name']} ({police_info['distance']:.0f} m) at {police_info['lat']}, {police_info['lon']}</p>"
    if fire_info:
        facility_text += f"<p>Nearest Fire Station: {fire_info['name']} ({fire_info['distance']:.0f} m) at {fire_info['lat']}, {fire_info['lon']}</p>"
    facility_text += f"<p>Control Center Location: {CONTROL_CENTER[0]}, {CONTROL_CENTER[1]}</p>"

    subject = f"Emergency Alert: {accident_type.capitalize()} Accident Detected"
    body = f"""<p>An {accident_type} accident has been detected.</p>
<p>Date & Time: {details.get('time')}</p>
<p>Accident Location: {details.get('location')}</p>
<p>Details: {details.get('message', 'N/A')}</p>
{facility_text}
<p>Please dispatch emergency services immediately.</p>
"""
    sender = os.environ.get("GMAIL_SENDER")
    recipients = ", ".join(["strangesanjay003@gmail.com"])

    if attachment_path:
        message = create_message_with_attachment(sender, recipients, subject, body, attachment_path)
    else:
        message = create_message(sender, recipients, subject, body)
    try:
        service = get_gmail_service()
        sent_message = service.users().messages().send(userId="me", body=message).execute()
        print("Emergency email sent successfully. Message Id:", sent_message.get("id"))
    except Exception as e:
        print("Error sending email:", e)

ACCIDENT_LOCATIONS = {
    "fire_accident": (9.27, 77.75),
    "vehicular_accident": (9.43, 77.65)
}

accident_details = {}
processingActive = True

CLIENT = InferenceHTTPClient(
    api_url="https://detect.roboflow.com",
    api_key="pQadYZknZMaxG0rf93E0"
)
MODEL_ID = "incident_classification/23"

# Initialize blockchain ledger
blockchain = Blockchain()

@app.route("/")
def index():
    pendrive_path = os.environ.get("PENDRIVE_PATH", os.getcwd())
    return render_template("index.html", chain=blockchain.chain, pendrive_path=pendrive_path)

@app.route("/inference", methods=["POST"])
def inference():
    global accident_details, processingActive
    if not processingActive:
        return jsonify({"result": "System paused. Accident already detected."})
        
    data = request.get_json()
    if not data or 'image' not in data:
        return jsonify({"error": "No image data provided"}), 400

    _, encoded = data['image'].split(",", 1)
    image_data = base64.b64decode(encoded)

    temp_filename = f"temp_{uuid.uuid4().hex}.jpg"
    with open(temp_filename, "wb") as f:
        f.write(image_data)

    result = CLIENT.infer(temp_filename, model_id=MODEL_ID)
    predictions = result.get("predictions", [])
    output = "No incident detected"
    incident_detected = False

    if predictions:
        first_pred = predictions[0]
        detected_class = first_pred.get("class", "Unknown").lower()
        confidence = first_pred.get("confidence", 0)
        output = f"{detected_class.capitalize()} ({confidence*100:.1f}%)"
        
        if detected_class in ACCIDENT_LOCATIONS and confidence > 0.7:
            processingActive = False
            incident_detected = True
            accident_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            accident_loc = ACCIDENT_LOCATIONS[detected_class]
            accident_details = {
                "type": detected_class,
                "time": accident_time,
                "location": accident_loc,
                "message": output
            }
            blockchain.add_block(accident_details)
            send_emergency_email(detected_class, accident_details, attachment_path=temp_filename)
    if os.path.exists(temp_filename):
        os.remove(temp_filename)
        
    return jsonify({"result": output, "incident_detected": incident_detected})

@app.route("/status", methods=["GET"])
def status():
    return jsonify({
        "accident_details": accident_details,
        "current_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

@app.route("/ledger_data", methods=["GET"])
def ledger_data():
    return jsonify(blockchain.chain)

@app.route("/reset", methods=["POST"])
def reset():
    global accident_details, processingActive
    accident_details = {}
    processingActive = True
    return jsonify({"status": "System reset."})

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
