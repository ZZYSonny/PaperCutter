import json
from typing import *
from urllib.request import urlopen, urlretrieve
from numpy.typing import *
import shutil
from bs4 import BeautifulSoup
import urllib
import fitz
from PIL import Image
import numpy as np
import os
import re
tol=0.1

DEFAULT_INPUT_FOLDER='./in'
DEFAULT_OUTPUT_FOLDER='./out'
DEFAULT_TEMP_MERGE_FOLDER='./merge'
DEFAULT_TEMP_ARXIV_FOLDER='./arxiv'

def inRange(x:float,l:float,r:float) -> bool:
    return l<=x and x<=r

def naturalSort(xs:list[str]) -> list[str]:
    return sorted(
        xs,
        key=lambda s:int(re.sub('\D', '', s))
    )

class Border:
    def __init__(self, f:Callable[[int],NDArray]) -> None:
        '''Current line'''
        self.cur=0
        '''A function to read the i-th line'''
        self.scan=f
    
    def scanUntil(self,l,r) -> None:
        '''Advance the border line until the average color is in [l,r)'''
        while(inRange(np.average(self.scan(self.cur)),l,r)): 
            self.cur+=1
    
    def scanUntilEmpty(self) -> None:
        '''Advance the border line, until a line with no content is met, and remains in this line'''
        self.scanUntil(0,255-tol)
    
    def scanUntilContent(self) -> None:
        '''Advance the border line, until a line with full content is met, and remains in this line'''
        self.scanUntil(255-tol,255)


class CropPicture:
    def __init__(
        self,
        page: fitz.Page,
        attr: dict[str,bool]
    ) -> None:
        self.page=page
        pix = page.get_pixmap(colorspace='GRAY', alpha=False)
        img = Image.frombytes('L', [pix.width, pix.height], pix.samples)
        self.image=np.array(img)
        self.attr=attr
        (height,width)=self.image.shape
        self.TopBorder=Border(lambda i:self.image[i,:])
        self.BottomBorder=Border(lambda i:self.image[height-1-i,:])
        self.LeftBorder=Border(lambda i:self.image[:,i])
        self.RightBorder=Border(lambda i:self.image[:,width-1-i])
        '''Clean the white margin'''
        self.TopBorder.scanUntilContent()
        self.BottomBorder.scanUntilContent()
        self.LeftBorder.scanUntilContent()
        self.RightBorder.scanUntilContent()

    def setCropbox(self) -> None:
        height,width=self.image.shape
        _,_,pdfWidth,pdfHeight=self.page.rect
        self.page.set_cropbox(fitz.Rect([
            (self.LeftBorder.cur/width)*pdfWidth,
            (self.TopBorder.cur/height)*pdfHeight,
            (1-(self.RightBorder.cur/width))*pdfWidth,
            (1-(self.BottomBorder.cur/height))*pdfHeight
        ]))

def workFile(cropFunction, inPDF:fitz.Document):
    '''- crop white margin for each page
       - then apply cropFunction to further reduce margin
    '''
    bookmarkL1=[
        page-1 for lvl,title,page in inPDF.get_toc()
        if lvl==1
    ]
    for i,page in enumerate(inPDF):
        attr={
            'isFirst': i==0,
            'isBookmark': i in bookmarkL1
        }
        crop=CropPicture(page,attr)
        # TODO: split a page into two pages
        if cropFunction is not None: 
            cropFunction(crop)
        crop.setCropbox()

def mergeFolder(inFolderPath:str, outFilePath:str):
    '''- Merge all files under inFolderPath
       - And save to outFilePath
       - A bookmark is created for each file
        - bookmark of merged PDF is added under this bookmark
    '''
    outPDF=fitz.Document()
    outToC = []
    for fileName in naturalSort(os.listdir(inFolderPath)):
        nPageBefore = outPDF.page_count
        inPDF = fitz.open(inFolderPath+"/"+fileName)
        outPDF.insert_pdf(inPDF)
        inToC = inPDF.get_toc(simple = False)
        #Add an entry for the file
        entryName = os.path.splitext(fileName)[0]
        outToC.append([1, entryName, nPageBefore + 1])
        #Add bookmark in inPDF under the bookmark for file
        for item in inToC:
            item[0]+=1
            item[2]+=nPageBefore
            item[3]['page']+=nPageBefore
            outToC.append(item)
    outPDF.set_toc(outToC)
    outPDF.ez_save(outFilePath)

def mergeFiles(inFolderPath: str, inFiles:list[str], outFilePath:str):
    '''- Merge all files under inFolderPath
       - And save to outFilePath
       - A bookmark is created for each file
        - bookmark of merged PDF is added under this bookmark
    '''
    outPDF=fitz.Document()
    outToC = []
    for fileName in inFiles:
        nPageBefore = outPDF.page_count
        inPDF = fitz.open(inFolderPath+"/"+fileName)
        outPDF.insert_pdf(inPDF)
        inToC = inPDF.get_toc(simple = False)
        #Add an entry for the file
        entryName = os.path.splitext(fileName)[0]
        outToC.append([1, entryName, nPageBefore + 1])
        #Add bookmark in inPDF under the bookmark for file
        for item in inToC:
            item[0]+=1
            item[2]+=nPageBefore
            item[3]['page']+=nPageBefore
            outToC.append(item)
    outPDF.set_toc(outToC)
    outPDF.ez_save(outFilePath)

def cropFile(cropFunction, inFilePath:str, outFilePath: str):
    '''- Read `inFilePath`
       - Crop each page according to `process`
       - Save to `outFilePath`
    '''
    #Load input PDF
    inPDF = fitz.open(inFilePath)
    workFile(cropFunction, inPDF)
    inPDF.ez_save(outFilePath)

def cropFolder(cropFunction, inFolderPath:str=DEFAULT_INPUT_FOLDER, outFolderPath:str=DEFAULT_OUTPUT_FOLDER):
    '''- For every file in `inFolderPath`
       - `workFile` and save in a pdf of same name in `outFolderPath`    
    '''
    for inFileName in os.listdir(inFolderPath):
        if(inFileName.endswith("pdf")):
            inFilePath=inFolderPath+"/"+inFileName
            outFilePath=outFolderPath+"/"+inFileName
            cropFile(cropFunction, inFilePath, outFilePath)

def cropThenMerge(cropFunction, inFolderPath:str=DEFAULT_INPUT_FOLDER, outFilePath:str=DEFAULT_OUTPUT_FOLDER, tempDir:str=DEFAULT_TEMP_MERGE_FOLDER):
    if os.path.exists(tempDir): shutil.rmtree(tempDir)
    os.mkdir(tempDir)
    cropFolder(cropFunction, inFolderPath, tempDir)
    mergeFolder(tempDir, outFilePath)

def cropArxiv(cropFunction, url:str, outFileDir:str=DEFAULT_OUTPUT_FOLDER, tempDir:str=DEFAULT_TEMP_ARXIV_FOLDER):    
    titleCachePath=tempDir+"/title_cache"
    if not os.path.exists(titleCachePath):
        json.dump({}, open(titleCachePath, 'w'))
    titleCache=json.load(open(titleCachePath))
    
    paperTitle=""
    if url in titleCache:
        paperTitle=titleCache[url]
    else:
        titleURL='https://arxiv.org/abs/'+url
        html = BeautifulSoup(urlopen(titleURL).read())
        paperTitle = html.title.string.split('] ')[1]
        titleCache[url]=paperTitle
        json.dump(titleCache, open(titleCachePath, 'w'))

    pdfPath=tempDir+"/"+url+'.pdf'
    if not os.path.exists(pdfPath):
        pdfURL='https://arxiv.org/pdf/'+url+'.pdf'
        urlretrieve(pdfURL,pdfPath)
    
    outFilePath=outFileDir+'/'+paperTitle+'.pdf'
    cropFile(cropFunction, pdfPath, outFilePath)

def cropQNote(pic: CropPicture):
    if pic.attr['isFirst']:
        pic.BottomBorder.scanUntilEmpty()
        pic.BottomBorder.scanUntilContent()
    else:
        pic.TopBorder.scanUntilEmpty()
        pic.TopBorder.scanUntilContent()

def cropAKNote(pic: CropPicture):
    if pic.attr['isBookmark']:
        pic.BottomBorder.scanUntilEmpty()
        pic.BottomBorder.scanUntilContent()
    else:
        pic.TopBorder.scanUntilEmpty()
        pic.TopBorder.scanUntilContent()

def cropArxivPaper(pic: CropPicture):
    if pic.attr['isFirst']:
        pic.LeftBorder.scanUntilEmpty()
        pic.LeftBorder.scanUntilContent()
    pic.BottomBorder.scanUntilEmpty()
    pic.BottomBorder.scanUntilContent()
    pic.TopBorder.scanUntilEmpty()
    pic.TopBorder.scanUntilContent()

def cropNoMore(pic: CropPicture):
    pass

def cropBottomNumber(pic: CropPicture):
    pic.BottomBorder.scanUntilEmpty()
    pic.BottomBorder.scanUntilContent()
    if pic.BottomBorder.cur<90:
        pic.BottomBorder.scanUntilEmpty()
        pic.BottomBorder.scanUntilContent()



def downloadArray(files: list[Tuple[str,str]], outFolderPath:str):
    for [url,filename] in files:
        urlretrieve(url, outFolderPath + '/' + filename)

def recreateDir(tempDir:str):
    if os.path.exists(tempDir): shutil.rmtree(tempDir)
    os.mkdir(tempDir)

#cropFolder('./in', './out', cropAKNote)
#cropThenMerge('./in','./out/merged.pdf', cropAKNote, './temp')
#cropArxiv(cropArxivPaper, '2011.03854')
#cropArxiv(cropArxivPaper, '1905.09550')

#cropThenMerge(cropNoMore, './in', './out/merge.pdf')

