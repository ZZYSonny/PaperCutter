import fitz
import re
import os
import shutil
from xml.dom import minidom
import requests

DEFAULT_INPUT_FOLDER='./in'
DEFAULT_OUTPUT_FOLDER='./out'
DEFAULT_TEMP_MERGE_FOLDER='./temp/merge'
DEFAULT_TEMP_ARXIV_FOLDER='./temp/arxiv'
DEBUG_PRINT_PAGE = []

filter_functions = [
    lambda s: s.startswith("arXiv:"),
    lambda s: s.startswith("Published as a conference paper at"),
    lambda s: s.lstrip().rstrip().isdigit(),
    lambda s: re.match("[0-9]\\.[0-9]\\.", s) is not None,
    lambda s: re.match("CHAPTER [0-9]\\.", s) is not None,
    lambda s: s == "PRIME AI paper"
]
custom_filter_functions = []

def common_filter_function(title:str):
    global filter_functions
    filter_functions.append(
        lambda s: s==title
    )

def filter_text(text:str) -> bool:
    '''Check if a text span should be kept'''
    return any(f(text) for f in filter_functions + custom_filter_functions)

def sort_files(xs:list[str], inFolderPath:str) -> list[str]:
    '''Sort filename in a more pleasant order'''
    return sorted(
        xs,
        key=lambda s:os.path.getctime(os.path.join(inFolderPath, s))
    )

def include_box(cropbox:list[int], bbox: list[int]):
    return (cropbox[0] <= bbox[0]
        and cropbox[1] <= bbox[1]
        and cropbox[2] >= bbox[2]
        and cropbox[3] >= bbox[3]
    )

def union_box(box:list[int], bbox:list[int]):
    '''Union two boxes in pdf'''
    box[0] = min(box[0], bbox[0])
    box[1] = min(box[1], bbox[1])
    box[2] = max(box[2], bbox[2])
    box[3] = max(box[3], bbox[3])

def crop_page(page:fitz.Page, i:int):
    '''Crop a page'''
    box = [float("inf"), float("inf"), float("-inf"), float("-inf")]
    texts=page.get_textpage().extractDICT()
    for block in texts["blocks"]:
        for line in block["lines"]:
            for span in line["spans"]:
                if not filter_text(span["text"]):
                    if i in DEBUG_PRINT_PAGE: print(span["text"])
                    union_box(box, span["bbox"])

    for [kind, rect] in page.get_bboxlog():
        if kind in ["fill-path", "stroke-path", "fill-image", "fill-shade"]:
            if include_box(page.cropbox, rect) and abs(rect[3]-rect[1]) > 32:
                union_box(box, rect)
    box[1] = max(0, box[1])
    if not box == [float("inf"), float("inf"), float("-inf"), float("-inf")]:
        try:
            page.set_cropbox(box)
        except:
            print("Error in page", i)


def crop_doc(inPath: str, outPath: str):
    '''Crop a document, and save to'''
    in_pdf = fitz.open(inPath)
    #for i in [61]:
    #    crop_page(in_pdf[i])
    for i,page in enumerate(in_pdf):
        crop_page(page,i)
    in_pdf.ez_save(outPath)

def merge_files(inFiles:list[str], outFilePath:str):
    '''- Merge all files in inFiles and save to outFilePath
       - A bookmark (with original bookmark) is created for each file.
    '''
    out_pdf = fitz.Document()
    out_toc = []
    for fileName in inFiles:
        nPageBefore = out_pdf.page_count
        inPDF = fitz.open(fileName)
        out_pdf.insert_pdf(inPDF)
        inToC = inPDF.get_toc(simple = False)
        #Add an entry for the file
        name = inPDF.metadata["title"]
        if name is None or name == "":
            name = os.path.splitext(os.path.split(fileName)[-1])[0]
        out_toc.append([1, name, nPageBefore + 1])
        #Add bookmark in inPDF under the bookmark for file
        for item in inToC:
            item[0]+=1
            item[2]+=nPageBefore
            item[3]['page']+=nPageBefore
            out_toc.append(item)
    out_pdf.set_toc(out_toc)
    out_pdf.ez_save(outFilePath)

def crop_folder(inFolderPath:str=DEFAULT_INPUT_FOLDER, outFolderPath:str=DEFAULT_OUTPUT_FOLDER):
    '''Crop all document in inFolderPath and save each individually to outFolderPath    
    '''
    for f in os.listdir(inFolderPath):
        if(f.endswith("pdf")):
            in_path=os.path.join(inFolderPath,f)
            out_path=os.path.join(outFolderPath,f)
            crop_doc(in_path, out_path)

def merge_folder(inFolderPath:str, outFilePath:str):
    '''Merge all files in inFolderPath and save to outFilePath
    '''
    merge_files(
        [os.path.join(inFolderPath, f) for f in sort_files(os.listdir(inFolderPath), inFolderPath)],
        outFilePath
    )

def crop_then_merge(inFolderPath:str=DEFAULT_INPUT_FOLDER, outFilePath:str=DEFAULT_OUTPUT_FOLDER, tempDir:str=DEFAULT_TEMP_MERGE_FOLDER):
    '''Crop all document in inFolderPath and merge all to outFolderPath
    '''
    if os.path.exists(tempDir): shutil.rmtree(tempDir)
    os.mkdir(tempDir)
    crop_folder(inFolderPath, tempDir)
    merge_folder(tempDir, outFilePath)

def crop_arxiv(id:str, outFileDir:str=DEFAULT_OUTPUT_FOLDER, tempDir:str=DEFAULT_TEMP_ARXIV_FOLDER):    
    '''Download (with cache) and crop a paper on Arxiv '''
    in_path = ""
    for fname in os.listdir(tempDir):
        if fname.startswith(f"[{id}]"):
            in_path = os.path.join(tempDir, fname)
            title = fname.split(".pdf")[0].split("] ")[1]
    
    url_info = f"https://export.arxiv.org/api/query?id_list={id}&max_results=1"
    url_file = f"https://arxiv.org/pdf/{id}.pdf"
    if in_path == "":
        meta_str = requests.get(url_info).text
        meta_xml = minidom.parseString(meta_str).getElementsByTagName("feed")[0].getElementsByTagName("entry")[0]
        title = meta_xml.getElementsByTagName("title")[0].childNodes[0].data
        in_path = os.path.join(tempDir, f"[{id}] {title}.pdf")
        with open(in_path, "wb") as f:
            for chunk in requests.get(url_file).iter_content(16*1024):
                f.write(chunk)
    
    common_filter_function(title)
    out_path=os.path.join(outFileDir, os.path.split(in_path)[1])
    crop_doc(in_path, out_path)
