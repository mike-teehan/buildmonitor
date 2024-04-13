#!/usr/bin/env python

from flask import Flask, render_template, request, Response, send_file, redirect, url_for, send_from_directory, json
import os
from PyPDF2 import PdfReader

app = Flask(__name__)

UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

"""
def is_valid_pdf(pdf_path):
    try:
        with open(pdf_path, 'rb') as file:
            reader = PdfReader(file)
            # Accessing number of pages to ensure the PDF is valid
            _ = len(reader.pages)
            return True
    except Exception as e:
        print(f"Error checking PDF file '{pdf_path}': {e}")
        return False

def create_working_dir(pdf_filename):
    try:
        # Split the filename from its extension
        filename_without_extension, _ = os.path.splitext(pdf_filename)

        # Construct the working directory path
        working_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'working_dir', filename_without_extension)

        # Create the directory if it doesn't exist
        os.makedirs(working_dir, exist_ok=True)

        # Construct the full path to the new file location in the working directory
        new_file_path = os.path.join(working_dir, pdf_filename)

        return new_file_path
    except Exception as e:
        print(f"Error creating working directory for '{pdf_filename}': {e}")
        return None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if request.method == 'POST':
        pdf_file = request.files['file']
        if pdf_file:
            pdf_filename = pdf_file.filename
            pdf_filename_without_ext = os.path.splitext(pdf_filename)[0]
            pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], pdf_filename_without_ext, pdf_filename)
            os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
            pdf_file.save(pdf_path)

            # Check if the uploaded PDF is valid
            if is_valid_pdf(pdf_path):
                # Generate a URL for the PDF file
                pdf_url = url_for('uploaded_file', filename=pdf_filename_without_ext + '/' + pdf_filename, _external=True)

                # Redirect to capture snapshot for the first page
                return render_template('capture.html', file_url=pdf_url)
            else:
                # PDF file is not valid, display error message
                return "Failed to upload PDF file. Please upload a valid PDF."
    return "No file uploaded"

# Route for viewing pdf files from capture.html

@app.route('/upload/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/capture/<path:filename>')
def capture(filename):
    file_url = url_for('uploaded_file', filename=filename, _external=True)
    return render_template('capture.html', file_url=file_url)


# Route for capturing snapshots
@app.route('/capture-snapshot/<path:pdf_path>')
def capture_snapshots(pdf_path):
    return render_template('capture.html', filename=pdf_path)

@app.route('/handle-snapshot', methods=['POST'])
def handle_snapshot():
    # Extract the snapshot data from the request
    snapshot_data = request.get_json()

    # TODO: Process the snapshot data

    # Return a success response
    return jsonify({'status': 'success'})
"""

from PIL import Image, ImageDraw, ImageFont
import io
import requests
import datetime

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

@app.route('/res/<path:name>', methods=['GET'])
def res(name):
    return send_from_directory('res/', name, as_attachment=True)

@app.route('/job/<jobname>', methods=['GET', 'PUT'])
def getjob(jobname):
#    name = request.args.get('pdf')
    if request.method == 'GET':
        exists = os.path.isfile(f"job/{jobname}.pdf")
        if not exists:
            return "NERT FOOND", 404
        return json.jsonify({"status": exists})
    if request.method == 'PUT':
        return

@app.route('/camera', methods=['GET'])
def camera():
    r = requests.get('http://localhost:5000/res/webcam.jpg')
#    return Response(io.BytesIO(r.content), mimetype='image/jpg')
    with Image.open(io.BytesIO(r.content)) as im:
        im2 = im.copy()
        draw = ImageDraw.Draw(im2)
        font = ImageFont.truetype("arial.ttf", 50)
        draw.text((0, 0), datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S"), (255, 255, 180), font=font)
        tmpimg = io.BytesIO()
        im2.save(tmpimg, format='JPEG')
        return Response(tmpimg.getvalue(), mimetype='image/jpg')

if __name__ == '__main__':
    app.run(host='::0', port=5000, debug=True)

