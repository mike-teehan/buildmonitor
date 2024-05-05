#!/usr/bin/env python

from flask import Flask, render_template, request, Response, send_file, redirect, url_for, send_from_directory, json
from PIL import Image, ImageDraw, ImageFont, ImageStat
from geventwebsocket.websocket import WebSocket
from werkzeug.routing import Rule
from flask_sockets import Sockets
from typing import Optional
from pathlib import Path
import requests
import datetime
import socket
import time
import math
import glob
import uuid
import fitz
import sys
import io
import re
import os

app:Flask = Flask(__name__)
sockets:Sockets = Sockets(app)

app.config.update(
    FLASK_APP="buildmonitor",
    RES_FOLDER = "res",
    JOB_FOLDER = "data/job",
    IMPORT_FOLDER = "data/import",
    COMPLETE_FOLDER = "data/complete"
)

@sockets. .on('connect')
def onconnect(e):
    print(f"{e=}")
    pass

# https://github.com/jgelens/gevent-websocket/blob/master/geventwebsocket/websocket.py
@sockets.route('/ws', websocket=True)
def any_event(ws: WebSocket):

    print(f"{ws=}")
#    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM | socket.SOCK_NONBLOCK)
    msg = ws.receive()
    print(f"{msg}")

    msg = ws.receive()
    print(f"{msg}")
    msg = ws.receive()
    print(f"{msg}")
    msg = ws.receive()
    print(f"{msg}")
    pass
sockets.url_map.add(Rule('/ws', endpoint=any_event, websocket=True))

#@socketio.on('connect')
#def ws(auth):
#    print(f"{auth=}")
#def ws(ws: SocketIO):
#    data = ws.receive()
#    print(f"{data=}")

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html', camerafps=0.5, pos="float")

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
def joblist() -> Response:
    filter = request.values.get("selectsearch")
    jobs = getjobs(filter)
#    print(f"{jobs=}")
#    hxattrs = []
#    for job in jobs:
#        hxattrs.append(f"hx-get=\"job/{job}\" hx-target=\"#workview\"")
    return Response(render_template('listoptions.html', category="job", items=jobs))

@app.route('/camera', methods=['GET'])
def camera() -> Response:
    """ sends a Response with a jpeg of a camera snapshot overlaid with a timestamp

    Args:
        none

    Returns:
        jpeg image over http
    """
    posstr:str = request.args.get("pos")

    # try to get a new image over http
    try:
        r = requests.get('http://localhost:8080/?action=snapshot')
    except requests.exceptions.ConnectionError as connerr:
        return Response("failed to connect to camera", status=500)

    # open the requested image
    with Image.open(io.BytesIO(r.content)) as im:
        # try to make a copy of it
        try:
            im2 = im.copy()
        except OSError as err:
            return Response(f"OSError: {err}", status=500)

        # add the timestamp to the copy
        im2 = addcameratimestamp(im2, posstr)

        # convert to jpeg bytes
        tmpimg = io.BytesIO()
        im2.save(tmpimg, format='JPEG')

        # return jpeg image
        return Response(tmpimg.getvalue(), mimetype='image/jpg')

def addcameratimestamp(im: Image.Image, pos: str = "ll") -> Optional[Image.Image]:
    """Adds a timestamp to the image at pos

    Args:
        im: the image to timestamp
        pos: "ul" = upper left, "ll" = lower left, "float" = move

    Returns:
        timestamped image
    """
    pos = pos if pos in ['ul', 'll', 'float'] else "ll"
    # load default font
    font = ImageFont.truetype("VT323-Regular.ttf", 32)
    # make timestamp string using datetime strftime()
    timestampstr = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S.%f%Z")
    # get x and y size of the timestamp string rendered in the font
    _, _, fx2, fy2 = font.getbbox(timestampstr)

    xpos = None
    ypos = None
    if(pos == "ul"):
        xpos = 0
        ypos = 0
    if(pos == "ll"):
        xpos = 0
        ypos = im.height - fy2
    if(pos == "float"):
        # number of steps in a one-way trip across the screen
        xsteps = 29
        ysteps = 61
        # use epoch time to calulate which step of the total trip back and forth
        xstep = time.time() % (xsteps * 2)
        ystep = time.time() % (ysteps * 2)
        # once step is greater than steps, pstep starts to count back down to zero instead of up to steps * 2
        pxstep = xstep if xstep < xsteps else xsteps - (xstep - xsteps)
        pystep = ystep if ystep < ysteps else ysteps - (ystep - ysteps)
        # use pstep/steps ratio to scale the xpos up to the image width minus rendered font width
        xpos = (pxstep / xsteps) * (im.width - fx2)
        ypos = (pystep / ysteps) * (im.height - fy2)

    # add the text to the image
    im = imageaddtext(im, font=font, x=xpos, y=ypos, text=timestampstr)

    return im

# type for typing savings
bmrgb = tuple[int, int, int]
def imageaddtext(im: Image.Image, font: ImageFont = ImageFont.truetype("VT323-Regular.ttf", 24),
                  x: int = 0, y: int = 0, text: str = "", lightcolor: bmrgb = (255, 255, 180),
          darkcolor: bmrgb = (0, 0, 75)) -> Optional[Image.Image]:
    """Adds text with a transparent gray background to im at (x,y) using font
        the color of the text is selected from lightcolor or darkcolor by the 
        brightness of the region where it would be rendered

    Args:
        im: the image to add the text to
        font: the font to use for the text
        x: render the text at x coord in im
        y: render the text at y coord in im
        text: the text string to render
        lightcolor: light colored bmrgb tuple (red, green, blue)
        darkcolor: dark colored bmrgb tuple (red, green, blue)
    
    Returns:
        image with text and background added
    """

    # render text with font and get the bounding box size
    fx0, fy0, fx1, fy1 = font.getbbox(text)
    # calulate font width and heigh
    fw:int = fx1 - fx0
    fh:int = fy1 - fy0
    # crop im to just the region covered by the text and convert it to grayscale
    fa = im.crop(box=(x, y, x + fx1, y + fy1)).convert('L')
    # prepare for some cropped image stats
    stat = ImageStat.Stat(fa)
    # use the rms brightness to determine light or dark text
    fill:bmrgb = lightcolor if stat.rms[0] < 100 else darkcolor

    # make a draw object with mode RGBA for blending
    draw = ImageDraw.Draw(im, mode="RGBA")
    # draw a semi-transparent rectangle where the font will be drawn
    draw.rectangle(xy=(x - 6, y, x + fa.width + 6, y + fa.height + 6), fill=(128, 128, 128, 96))
    # draw the text over the rectangle
    draw.text(xy=(x, y), text=text, fill=fill, font=font)

    return im

@app.route('/job/<name>/image', methods=['GET'])
def jobnameimage(name: str) -> Response:
    return send_file(f"job/{name}/doc-0000.png")

@app.route('/job/<name>/complete', methods=['GET'])
def jobnamecomplete(name: str) -> Response:
    jobdir = f"{app.config['JOB_FOLDER']}/{name}"
#    jobdocfile = f"{jobdir}/{}"
    return send_file(f"job/{name}/{name}.png")

@app.route('/job/<name>/snapshot/list', methods=['GET'])
def jobnamesnapshotlist(name: str) -> Response:
    jobdir = f"{app.config['JOB_FOLDER']}/{name}"
    files = sorted(Path(jobdir).iterdir(), key=os.path.basename, reverse=True)
    snaps = []
    for file in files:
        print(f"{file.name=}")
        res = re.search('([0-9][0-9][0-9][0-9]).jpg', file.name)
        if res:
            print(f"{file.name=} matched")
            snaps.append(f"{res.group(1)}")

    return Response(render_template("capturegriditem.html", name=name, snaps=snaps, camerafps=5))

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
def jobname(name: str) -> Response:
    return Response(render_template("jobcapture.html", name=name))

@app.route('/import', methods=['GET'])
def jobcreate_get() -> Response:
    return Response(render_template('jobimport.html'))

@app.route('/import/<pdfid>/<pagenum>/create', methods=['POST'])
def jobimportcreate(pdfid, pagenum) -> Response:
    jobname = request.values.get("jobname")
    if not len(jobname) > 0:
        return Response("no jobname", status=404)

    cliprect = request.values.get("cliprect")
    if not cliprect:
        cliprect = [ 0.0, 0.0, 1.0, 1.0 ]

    try:
        with fitz.open(f"{app.config['IMPORT_FOLDER']}/{pdfid}.pdf") as pdfdoc:
            # page count
            pagecnt = pdfdoc.page_count
            # pdf numbers pages beginning at 1... python lists start at 0
            page = pdfdoc[int(pagenum) - 1]
            # medium res
            pagepix = page.get_pixmap(dpi=300)
    except fitz.mupdf.FzErrorFormat as err:
        return Response(404)

    if not os.path.isdir(f"{app.config['JOB_FOLDER']}/{jobname}"):
        os.mkdir(f"{app.config['JOB_FOLDER']}/{jobname}")
    if not os.path.isdir(f"{app.config['JOB_FOLDER']}/{jobname}"):
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

    files = glob.glob(f"{app.config['JOB_FOLDER']}/{pdfid}/doc-*.png")
    greatest = -1
    for file in files:
        res = re.search("^doc-([0-9][0-9][0-9][0-9]).png$")
        if res:
            i = int(res.group(1))
            greatest = i if i > greatest else greatest
    docname = f"doc-{str(greatest + 1).zfill(4)}"
    # save the cropped images as a png to a bytesio
    cropimg.save(f"{app.config['JOB_FOLDER']}/{jobname}/{docname}.png", format="PNG")

    headers = { "HX-Trigger-After-Settle": "updatejob" }
    return Response(render_template("ocrcontrols.html", page=pagenum, pagecnt=pagecnt, pdfid=pdfid, jobname=jobname), headers=headers)

@app.route('/import/list', methods=['GET'])
def jobimportlist() -> Response:
    importfilter = request.values.get("importsearch")
    importfilter = importfilter if importfilter else ""

    pdffiles = glob.glob(f"{app.config['IMPORT_FOLDER']}/*.pdf")
    ret:list = []
    for pdffile in pdffiles:
        res = re.search(f"{app.config['IMPORT_FOLDER']}/(.*)\.pdf", pdffile)
        if res:
            pdfid = res.group(1)
            if len(importfilter) == 0 or importfilter in pdfid:
                ret.append(pdfid)

    return Response(render_template('listoptions.html', category="import", items=ret))

# display the job create ocr view
@app.route('/import/<pdfid>/<pagenum>/ocr', methods=['GET'])
def importocrview(pdfid, pagenum):
    pagecnt = request.args.get("pagecnt")
    return render_template('jobcreate.html', pdfid=pdfid, page=pagenum, pagecnt=pagecnt, ocrcursize=[ 100, 33 ])

# perform ocr on a cropped region of a page in {pdfid}.pdf then update the page controls
@app.route('/import/<pdfid>/<pagenum>/ocr', methods=['POST'])
def jobcreatepdfocr_get(pdfid, pagenum) -> Response:
    # open the file {pdfid}.pdf, get the page count and grab a pixmap of page {pagenum}
    pagecnt = False
    page = False
    pagepix = False
    try:
        with fitz.open(f"{app.config['IMPORT_FOLDER']}/{pdfid}.pdf") as pdfdoc:
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
@app.route('/import/<pdfid>/<pagenum>', methods=['GET'])
def jobcreatepdf_get(pdfid, pagenum) -> Response:
    fmt = request.args.get("format")
    if not fmt:
        fmt = "jpg"
    if fmt not in ["png", "jpg", "pdf"]:
        return Response(404)
    try:
        with fitz.open(f"{app.config['IMPORT_FOLDER']}/{pdfid}.pdf") as pdfdoc:
            page = pdfdoc[int(pagenum) - 1]
            img = page.get_pixmap().tobytes(output=fmt)
            return Response(img, mimetype=f"image/{fmt}", direct_passthrough=True)
    except fitz.mupdf.FzErrorFormat as err:
        return Response(404)

# upload a pdf to import jobs from and save it with a randomized name
@app.route('/import', methods=['POST'])
def importpost_post() -> Response:
    # get the bytes of the uploaded pdf
    pdf = request.files['newjobpdf']
    pdfid = Path(pdf.filename).stem
    fio = io.BytesIO(pdf.read())

    # make sure it is a pdf and not just any format fitz can open
    pagecnt = False
    try:
        with fitz.open(stream=fio) as pdfdoc:
            if pdfdoc.is_pdf:
                pagecnt = pdfdoc.page_count
    except fitz.mupdf.FzErrorFormat as err:
        print(f"{err=}")

    if not pagecnt:
        return Response({ "success": False }, status=500)

    # reset the bytesio so we can read it again
    fio.seek(0)
    # random file name
    #pdfid = uuid.uuid4().hex
    # write the pdf to disk
    with open(f"{app.config['IMPORT_FOLDER']}/{pdfid}.pdf", "wb") as f:
        f.write(fio.getbuffer())

    headers = { "HX-Trigger-After-Settle": "updateimport" }
    return Response(render_template('jobcreate.html', pdfid=pdfid, page=1, pagecnt=pagecnt, ocrcursize=[ 100, 33 ]), headers=headers)

@app.route('/complete/list', methods=['GET'])
def jobcompletelist() -> Response:
    items:list = []
    return Response(render_template('listoptions.html', category="complete", items=items))

def getjobs(filter: str="") -> list:
    """Gets a list of job name by iterating all the subfolders of JOB_FOLDER ordered by mtime

    Args:
        filter: text to filter on or "" for no filter

    Returns:
        list of job names
    """
    filter = filter if filter else ""
    # ALL CAPS CONST
    JOBDIR = f"{app.config['JOB_FOLDER']}/"
    # list of jobnames that pass the filter
    jobs:list = []
    # get a list of dir items sorted by mytime
    dirs = sorted(Path(JOBDIR).iterdir(), key=os.path.getmtime)
    for dir in dirs:
        # ignore all files
        if dir.is_file():
            continue
        # slice JOBDIR off the beginning of the dir string
        dirname = str(dir)[len(JOBDIR):]
        # only append if filter length is zero or filter exists as a substring in dirname
        if len(filter) == 0 or filter.lower() in dirname.lower():
            jobs.append(dirname)

    return jobs
#    for root, dirs, files in os.walk(JOBDIR):
#        for dir in dirs:
#            if len(filter) > 0:
#                if filter.lower() in dir.lower():
#                    jobs.append(dir)
#            else:
#                jobs.append(dir)
#            print(f"dir: {dir}")
#    for x in jerbs:
#        print(f"|{x}|")

def checkdirs() -> bool:
    """Checks that the folders in checkdirs exist, same for mkdirs but also attempts to make them

    Args:
        none

    Returns:
        True if all dirs exist, False otherwise
    """
    # res folder is part of git, it should always exist
    checkdirs = [ app.config['RES_FOLDER'] ]
    # these folders are made if they don't already exist
    mkdirs = [ app.config['JOB_FOLDER'], app.config['IMPORT_FOLDER'], app.config['COMPLETE_FOLDER'] ]

    # if allgood goes False at any point it will stay that way
    allgood = True
    for dir in checkdirs:
        allgood = allgood and direxists(dir)
    for dir in mkdirs:
        allgood = allgood and direxists(dir, mkdir=True)

    return allgood

def direxists(dir: str, mkdir: bool=False) -> bool:
    """Check if directory dir exists, attempt to make it if mkdir is True

    Args:
        dir: path to directory
        mkdir: when True, attempt to make the directory if it doesn't exist
    
    Returns:
        True if dir exists, False otherwise
    """
    # only attempt to make dir if dir doesn't currently exist and  mkdir is True
    if os.path.isdir(dir) != True and mkdir:
        os.makedirs(dir, exist_ok=True)

    # return the final check
    return True if os.path.isdir(dir) else False

if __name__ == '__main__':
    checkdirs()
#    socketio.run(app, host='::0', port=5000, debug=True)
    from gevent import pywsgi
    from geventwebsocket.handler import WebSocketHandler
    server = pywsgi.WSGIServer(('::0', 5000), app, handler_class=WebSocketHandler)
    print('server start')
    server.serve_forever()
