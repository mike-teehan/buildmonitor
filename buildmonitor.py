#!/usr/bin/env python

from flask import Flask, render_template, request, Response, send_file, redirect, url_for, send_from_directory, json
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import requests
import datetime
import glob
import uuid
import fitz
import sys
import io
import re
import os

app = Flask(__name__)

app.config.update(
    FLASK_APP="buildmonitor",
    RES_FOLDER = "res",
    JOB_FOLDER = "job",
    IMPORT_FOLDER = "import",
    COMPLETE_FOLDER = "complete"
)

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

@app.route('/res/<path:name>', methods=['GET'])
def res(name):
    return send_from_directory(f"{app.config['RES_FOLDER']}/", name, as_attachment=True)

#@app.route('/job/<jobname>', methods=['GET'])
#def getjob(jobname):
#    name = request.args.get('pdf')
#    if request.method == 'GET':
#        exists = os.path.isfile(f"{app.config['RES_FOLDER']}/{jobname}.pdf")
#        if not exists:
#            return "NERT FOOND", 404
#        return json.jsonify({"status": exists})

@app.route('/job/list', methods=['GET'])
def joblist():
    filter = request.values.get("selectsearch")
    jobs = getjobs(filter)
    hxattrs = []
    for job in jobs:
        hxattrs.append(f"hx-get=\"job/{job}\" hx-target=\"#workview\"")
    return htmloptions(jobs, hxattrs)

@app.route('/camera', methods=['GET'])
def camera() -> Response:
#    r = requests.get('http://localhost:5000/res/webcam.jpg')
    r = requests.get('http://localhost:8080/?action=snapshot')
#    return Response(io.BytesIO(r.content), mimetype='image/jpg')
    with Image.open(io.BytesIO(r.content)) as im:
        im2 = im.copy()
        draw = ImageDraw.Draw(im2)
        font = ImageFont.truetype("arial.ttf", 50)
        draw.text((0, 0), datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S"), (255, 255, 180), font=font)
        tmpimg = io.BytesIO()
        im2.save(tmpimg, format='JPEG')
        return Response(tmpimg.getvalue(), mimetype='image/jpg')

@app.route('/job/<name>/image', methods=['GET'])
def jobnameimage(name: str) -> Response:
    return send_file(f"job/{name}/{name}.png")

@app.route('/job/<name>/complete', methods=['GET'])
def jobnamecomplete(name: str) -> Response:
    jobdir = f"{app.config['JOB_FOLDER']}/{name}"
#    jobdocfile = f"{jobdir}/{}"
    return send_file(f"job/{name}/{name}.png")

@app.route('/job/<name>/snapshot/list', methods=['GET'])
def jobnamesnapshotlist(name: str):
    ret = ""
    jobdir = f"{app.config['JOB_FOLDER']}/{name}"
    greatest = 0
    files = sorted(Path(jobdir).iterdir(), key=os.path.getmtime)
    snaps = []
    for file in files:
        print(f"{file.name=}")
        res = re.search('([0-9][0-9][0-9][0-9]).jpg', file.name)
        if res:
            print(f"{file.name=} matched")
            snaps.append(f"{res.group(1)}")
    for snap in snaps:
        ret += render_template("capturegriditem.html", name=name, snapnum=snap)
    return ret

@app.route('/job/<name>/snapshot/image/<snapnum>', methods=['GET'])
def jobnamesnapshotimagesnapnum(name: str, snapnum: int) -> Response:
    mini = (request.args.get("mini") == "1")
    jobdir = f"{app.config['JOB_FOLDER']}/{name}"
    filename = f"{jobdir}/{str(snapnum).zfill(4)}.jpg"
    if not Path(filename).is_file():
        return Response("No file", status=404)

    if not mini:
        return send_file(filename)
    
    img = Image.open(filename)
    aspectratio = img.height / img.width
    newheight = 100
    newwidth = newheight / aspectratio
    miniimg = img.resize([ int(newwidth), int(newheight) ], resample=Image.Resampling.LANCZOS, box=None)

    outbytes = io.BytesIO()
    miniimg.save(outbytes, format='JPEG')
    return Response(outbytes.getvalue(), mimetype='image/jpg')

@app.route('/job/<name>/snapshot', methods=['GET'])
def jobnamesnapshot(name: str) -> Response:
    r = requests.get('http://localhost:5000/camera')
    jobdir = f"{app.config['JOB_FOLDER']}/{name}"
    greatest = -1
    files = sorted(Path(jobdir).iterdir(), key=os.path.getmtime)
    for file in files:
        res = re.search('([0-9][0-9][0-9][0-9]).jpg', file.name)
        if res:
            snapnum = int(res.group(1))
            greatest = snapnum if snapnum > greatest else greatest

    nusnapnum = f"{ greatest + 1}".zfill(4)
    filename = f"{nusnapnum}.jpg"
    with open(f"{jobdir}/{filename}", "wb") as f:
        f.write(r.content)

    headers = { "HX-Trigger-After-Settle": "updatecapture" }
    return Response(render_template("jobcapture.html", name=name),  headers=headers)

@app.route('/job/<name>')
def jobname(name: str):
    return render_template("jobcapture.html", name=name)

@app.route('/job/import', methods=['GET'])
def jobcreate_get():
    return render_template('jobimport.html')

@app.route('/job/import/<pdfid>/<pagenum>/create', methods=['POST'])
def jobimportcreate(pdfid, pagenum) -> Response:
    jobname = request.values.get("jobname")
    if not len(jobname) > 0:
        return Response("no jobname", status=404)

    cliprect = request.values.get("cliprect")
    if not cliprect:
        cliprect = [ 0.0, 0.0, 1.0, 1.0 ]

    try:
        with fitz.open(f"job/{pdfid}.pdf") as pdfdoc:
            # page count
            pagecnt = pdfdoc.page_count
            # pdf numbers pages beginning at 1... python lists start at 0
            page = pdfdoc[int(pagenum) - 1]
            # medium res
            pagepix = page.get_pixmap(dpi=300)
    except fitz.mupdf.FzErrorFormat as err:
        return Response(404)

    if not os.path.isdir(f"job/{jobname}"):
        os.mkdir(f"job/{jobname}")
    if not os.path.isdir(f"job/{jobname}"):
        return Response("no job directory", status=404)

    pagepng = io.BytesIO(pagepix.tobytes(output="png"))
    # open that image with PIL
    pageimg = Image.open(pagepng)
    # calculate cropping coordinates from percentages using the actual image size
    x = int(pageimg.width * cliprect[0])
    y = int(pageimg.height * cliprect[1])
    w = int(pageimg.width * cliprect[2])
    h = int(pageimg.height * cliprect[3])
    # box 'em up (x1, y1, x2, y2) for cropping
    box = [ x, y, x + w, y + h ]
#    boxstr = ', '.join([str(e) for e in box])
#    print(f"box: {boxstr}", file=sys.stderr)
    # set the crop
    cropimg = pageimg.crop(box)

    files = glob.glob(f"job/{pdfid}/doc*.png")
    greatest = -1
    for file in files:
        res = re.search("^doc-([0-9][0-9][0-9][0-9]).png$")
        if res:
            i = int(res.group(1))
            greatest = i if i > greatest else greatest
    docname = f"doc-{str(greatest + 1).zfill(4)}"
    # save the cropped images as a png to a bytesio
    cropimg.save(f"job/{jobname}/{docname}.png", format="PNG")

    headers = { "HX-Trigger-After-Settle": "updatejob" }
    return Response(render_template("ocrcontrols.html", page=pagenum, pagecnt=pagecnt, pdfid=pdfid, jobname=jobname), headers=headers)

@app.route('/job/import/list', methods=['GET'])
def jobimportlist() -> Response:
    importfilter = request.values.get("importsearch")
    importfilter = importfilter if importfilter else ""

    pdffiles = glob.glob("job/*.pdf")
    ret = []
    hxattrs = []
    for pdffile in pdffiles:
        res = re.search('job/(.*)\.pdf', pdffile)
        if res:
            pdfid = res.group(1)
            if len(importfilter) == 0 or importfilter in pdfid:
                ret.append(pdfid)
                hxattrs.append(f"hx-get=\"job/import/{pdfid}/1/ocr\" hx-target=\"#workview\"")
    if len(ret) == 0:
        return Response(htmloptions([ "None" ], attrs=[ "disabled" ]))

    return Response(htmloptions(ret, attrs=hxattrs))

# display the job create ocr view
@app.route('/job/import/<pdfid>/<pagenum>/ocr', methods=['GET'])
def importocrview(pdfid, pagenum):
    pagecnt = request.args.get("pagecnt")
    return render_template('jobcreate.html', pdfid=pdfid, page=pagenum, pagecnt=pagecnt, ocrcursize=[ 100, 33 ])

# perform ocr on a cropped region of a page in {pdfid}.pdf then update the page controls
@app.route('/job/import/<pdfid>/<pagenum>/ocr', methods=['POST'])
def jobcreatepdfocr_get(pdfid, pagenum) -> Response:
    # open the file {pdfid}.pdf, get the page count and grab a pixmap of page {pagenum}
    pagecnt = False
    page = False
    pagepix = False
    try:
        with fitz.open(f"job/{pdfid}.pdf") as pdfdoc:
            # page count
            pagecnt = pdfdoc.page_count
            # pdf numbers pages beginning at 1... python lists start at 0
            page = pdfdoc[int(pagenum) - 1]
            # medium res
            pagepix = page.get_pixmap(dpi=300)
    except fitz.mupdf.FzErrorFormat as err:
#        headers = { "HX-Trigger-After-Settle": "updateimport" }
#        return Response(render_template("ocrcontrols.html", page=pagenum, pagecnt=pagecnt, pdfid=pdfid, jobname=type(err)),  headers=headers)
        return renderocrresponse(page=pagenum, pagecnt=pagecnt, pdfid=pdfid, jobname=type(err))

    # if the clipping rectangle doesn't seem right, bail
    ocrrectstr = request.values['ocrrect']
    if not 100 > len(ocrrectstr) > 10:
        return renderocrresponse(page=pagenum, pagecnt=pagecnt, pdfid=pdfid, jobname="")

    # try to parse the json
    try:
        ocrrect = json.loads(ocrrectstr)
    except ValueError as err:
        return renderocrresponse(page=pagenum, pagecnt=pagecnt, pdfid=pdfid, jobname=type(err))

    if not len(ocrrect) == 4:
        return renderocrresponse(page=pagenum, pagecnt=pagecnt, pdfid=pdfid, jobname="")

    # convert pixmap to png and store in a bytesio
    pagepng = io.BytesIO(pagepix.tobytes(output="png"))
    # open that image with PIL
    pageimg = Image.open(pagepng)
    # calculate cropping coordinates from percentages using the actual image size
    x = int(pageimg.width * ocrrect[0])
    y = int(pageimg.height * ocrrect[1])
    w = int(pageimg.width * ocrrect[2])
    h = int(pageimg.height * ocrrect[3])
    # box 'em up (x1, y1, x2, y2) for cropping
    box = [ x, y, x + w, y + h ]
#    boxstr = ', '.join([str(e) for e in box])
#    print(f"box: {boxstr}", file=sys.stderr)
    # set the crop
    cropimg = pageimg.crop(box)
    # save the cropped images as a png to a bytesio
    imgbytes = io.BytesIO()
    cropimg.save(imgbytes, format="PNG")

    # hopefully open imgbytes with fitz and ocr the entire image
    try:
        with fitz.open(stream=imgbytes) as ocrpage:
            page = ocrpage[0]
            tp = page.get_textpage_ocr(full=True, dpi=300, tessdata="/usr/share/tesseract-ocr/5/tessdata/")
            text = ' '.join(page.get_text(textpage=tp).split())
    except fitz.mupdf.FzErrorFormat as err:
#        headers = { "HX-Trigger-After-Settle": "updateimport" }
#        return Response(render_template("ocrcontrols.html", page=pagenum, pagecnt=pagecnt, pdfid=pdfid, jobname=type(err)),  headers=headers)
        return renderocrresponse(page=pagenum, pagecnt=pagecnt, pdfid=pdfid, jobname=type(err))

    # update the ocr controls
#    headers = { "HX-Trigger-After-Settle": "updateimport" }
#    return Response(render_template("ocrcontrols.html", page=pagenum, pagecnt=pagecnt, pdfid=pdfid, jobname=text),  headers=headers)
    return renderocrresponse(page=pagenum, pagecnt=pagecnt, pdfid=pdfid, jobname=text)

def renderocrresponse(page: int, pagecnt: int, pdfid: str, jobname: str) -> Response:
    headers = { "HX-Trigger-After-Settle": "updateimport" }
    return Response(render_template("ocrcontrols.html", page=page, pagecnt=pagecnt, pdfid=pdfid, jobname=jobname),  headers=headers)

# get a png, jpg, or pdf of a single page in the file {pdfid}.pdf
@app.route('/job/import/<pdfid>/<pagenum>', methods=['GET'])
def jobcreatepdf_get(pdfid, pagenum) -> Response:
    fmt = request.args.get("format")
    if not fmt:
        fmt = "jpg"
    if fmt not in ["png", "jpg", "pdf"]:
        return Response(404)
    try:
        with fitz.open(f"job/{pdfid}.pdf") as pdfdoc:
            page = pdfdoc[int(pagenum) - 1]
            img = page.get_pixmap().tobytes(output=fmt)
            return Response(img, mimetype=f"image/{fmt}", direct_passthrough=True)
    except fitz.mupdf.FzErrorFormat as err:
        return Response(404)

# upload a pdf to import jobs from and save it with a randomized name
@app.route('/job/import', methods=['POST'])
def jobcreate_post():
    # get the bytes of the uploaded pdf
    pdf = request.files['newjobpdf']
    pdfid = Path(pdf.filename).stem
    fio = io.BytesIO(pdf.read())
    res = re.search('job/(.*)\.pdf', pdf.filename)
    if res:
        pdfid = res.group(1)
    # make sure it is a pdf and not just any format fitz can open
    pagecnt = False
    try:
        with fitz.open(stream=fio) as pdfdoc:
            if pdfdoc.is_pdf:
                pagecnt = pdfdoc.page_count
    except fitz.mupdf.FzErrorFormat as err:
        print("Bad PDF Exception")

    if not pagecnt:
        return { "success": False }

    # reset the bytesio so we can read it again
    fio.seek(0)
    # random file name
    #pdfid = uuid.uuid4().hex
    # write the pdf to disk
    with open(f"job/{pdfid}.pdf", "wb") as f:
        f.write(fio.getbuffer())

    headers = { "HX-Trigger-After-Settle": "updateimport" }
    return Response(render_template('jobcreate.html', pdfid=pdfid, page=1, pagecnt=pagecnt, ocrcursize=[ 100, 33 ]), headers=headers)

@app.route('/job/complete/list', methods=['GET'])
def jobcompletelist() -> Response:
    return Response(htmloptions(['None']))

def htmloptions(options, attrs=[]):
    if len(attrs) != len(options):
        attrs = []
        for o in options:
            attrs.append("")

    ret = ""
    for i in range(0, len(options)):
        ret += f"<option {attrs[i]}>{options[i]}</option>"
    return ret

def getjobs(filter=""):
    filter = filter if filter else ""

    JOBDIR = 'job/'
    jobs = []
    dirs = sorted(Path(JOBDIR).iterdir(), key=os.path.getmtime)
    for dir in dirs:
        if dir.is_file():
            continue
        dirname = str(dir).replace("job/", "", 1)
        if len(filter) == 0 or filter.lower() in dirname.lower():
            jobs.append(dirname)

#    for root, dirs, files in os.walk(JOBDIR):
#        for dir in dirs:
#            if len(filter) > 0:
#                if filter.lower() in dir.lower():
#                    jobs.append(dir)
#            else:
#                jobs.append(dir)
    return jobs
#            print(f"dir: {dir}")
#    for x in jerbs:
#        print(f"|{x}|")

def checkdirs():
    # res folder
    checkdirs = [ app.config['RES_FOLDER'], app.config['JOB_FOLDER'], app.config['IMPORT_FOLDER'], app.config['COMPLETE_FOLDER'] ]

    allgood = True
    for dir in checkdirs:
        allgood = allgood and makedirifnotexist(dir)
    return allgood

def makedirifnotexist(dir):
    if not os.path.isdir(dir):
        os.mkdir(dir)
    return True if os.path.isdir(dir) else False

if __name__ == '__main__':
    app.run(host='::0', port=5000, debug=True)
