from typing import Callable
from numpy.typing import NDArray
from pdf2image import convert_from_path
from PyPDF2 import PdfFileWriter,PdfFileReader
from PyPDF2.generic import RectangleObject
import numpy as np
import os
import re
tol=0.2

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
        image:np.ndarray,
        cropBox:RectangleObject,
        attr: dict[str,bool]
    ) -> None:
        self.image=image
        self.attr=attr
        (height,width)=self.image.shape
        self.cropBox=cropBox
        self.TopBorder=Border(lambda i:image[i,:])
        self.BottomBorder=Border(lambda i:image[height-1-i,:])
        self.LeftBorder=Border(lambda i:image[:,i])
        self.RightBorder=Border(lambda i:image[:,width-1-i])
        '''Clean the white margin'''
        self.TopBorder.scanUntilContent()
        self.BottomBorder.scanUntilContent()
        self.LeftBorder.scanUntilContent()
        self.RightBorder.scanUntilContent()

    def toCropbox(self) -> RectangleObject:
        height=int(self.image.shape[0])
        width=int(self.image.shape[1])
        pdfWidth =int(self.cropBox.getUpperRight()[0])
        pdfHeight=int(self.cropBox.getUpperRight()[1])
        return RectangleObject([
            (self.LeftBorder.cur/width)*pdfWidth,
            (1-(self.TopBorder.cur/height))*pdfHeight,
            (1-(self.RightBorder.cur/width))*pdfWidth,
            (self.BottomBorder.cur/height)*pdfHeight
        ])


def work(
    images:np.ndarray, 
    inFile:PdfFileReader, 
    outFile:PdfFileWriter, 
    process
)->None:
    '''RuleCrop the file, and save to PdfFileWriter'''
    bookmarkL1 = [
        inFile.getDestinationPageNumber(b)
        for b in inFile.getOutlines()
        if '/Page' in b
    ]
    for i in range(len(images)):
        pic=CropPicture(
            image=np.array(images[i]),
            cropBox=inFile.getPage(i).cropBox,
            attr={
                'isFirst': i==0,
                'isBookmark': i in bookmarkL1
            }
        )
        for box in process(pic):
            newp=inFile.getPage(i)
            newp.cropBox=box.toCropbox()
            outFile.addPage(newp)

def copyBookmarks(outlines, inFile: PdfFileReader, outFile: PdfFileWriter, parent=None):
    '''Recursively add PyPDF2 bookmark to outFile'''
    last=None
    for b in outlines:
        if '/Title' in b:
            last=outFile.addBookmark(
                title=b.title, 
                pagenum=inFile.getDestinationPageNumber(b),
                parent=parent
            )
        else:
            copyBookmarks(b, inFile, outFile, last)

def workFile(inFilePath:str, outFilePath:str, process):
    '''- Read `inFilePath`
       - Crop each page according to `process`
       - Copy bookmarks
       - Save to `outFilePath`
    '''
    #Load input PDF
    inFile = PdfFileReader(open(inFilePath,"rb"))
    outFile= PdfFileWriter()
    
    #Crop for each page
    images = convert_from_path(inFilePath, grayscale=True)
    work(images, inFile,outFile, process)
    
    copyBookmarks(inFile.getOutlines(), inFile, outFile)

    #Save file to path
    with open(outFilePath,'wb') as outStream: 
        outFile.write(outStream) 

def workFolder(inFolderPath:str, outFolderPath:str, process):
    '''- For every file in `inFolderPath`
       - `workFile` and save in a pdf of same name in `outFolderPath`    
    '''
    for inFileName in os.listdir(inFolderPath):
        inFilePath=inFolderPath+"/"+inFileName
        outFilePath=outFolderPath+"/"+inFileName
        workFile(inFilePath, outFilePath, process)

def workFolderAndMerge(inFolderPath:str, outFilePath:str, process):
    '''- For every file in `inFolderPath`, in a natural ordering
       - Crop each page according to `process`
       - Add a bookmark as entry for every file
    '''
    outFile= PdfFileWriter()
    for fileName in naturalSort(os.listdir(inFolderPath)):
        print("Start: "+fileName)
        nPageBefore=outFile.getNumPages()
        work(inFolderPath+"/"+fileName,outFile, process)
        pdfName=fileName.split("/")[-1].split(".")[0]
        outFile.addBookmark(pdfName,nPageBefore , parent=None)
    print("Saving")
    with open(outFilePath,'wb') as outStream: outFile.write(outStream) 

def processNothing(pic: CropPicture) -> list:
    return [pic]

def processQNote(pic: CropPicture) -> list :
    if pic.attr['isFirst']:
        pic.BottomBorder.scanUntilEmpty()
        pic.BottomBorder.scanUntilContent()
    else:
        pic.TopBorder.scanUntilEmpty()
        pic.TopBorder.scanUntilContent()
    return [pic]

def processAKNote(pic: CropPicture) -> list:
    if pic.attr['isBookmark']:
        pic.BottomBorder.scanUntilEmpty()
        pic.BottomBorder.scanUntilContent()
    else:
        pic.TopBorder.scanUntilEmpty()
        pic.TopBorder.scanUntilContent()
    return [pic]

def processArxiv(pic: CropPicture) -> list :
    if pic.attr['isFirst']:
        pic.LeftBorder.scanUntilEmpty()
        pic.LeftBorder.scanUntilContent()
    return [pic]

#workFile("./in/1.pdf","./out/1.pdf")
workFolder("./in","./out", processAKNote)
#workFolderAndMerge("./in","./out/1.pdf")