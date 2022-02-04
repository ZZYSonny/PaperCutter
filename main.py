from typing import Callable
from numpy.typing import NDArray
from pdf2image import convert_from_path
from PyPDF2 import PdfFileWriter,PdfFileReader
import numpy as np
import os
import re

tol=0.2

def inRange(x:float,l:float,r:float) -> bool:
    return l<=x and x<=r

class Border:
    def __init__(self, f:Callable[[int],NDArray]) -> None:
        '''Current line'''
        self.cur=0
        '''A function to read the i-th line'''
        self.scan=f
    
    '''Advance the border line until the average color is in [l,r)'''
    def scanUntil(self,l,r) -> None:
        while(inRange(np.average(self.scan(self.cur)),l,r)): 
            self.cur+=1
    
    '''Advance the border line, until a line with no content is met, and remains in this line'''
    def scanUntilEmpty(self) -> None:
        self.scanUntil(0,255-tol)
    
    '''Advance the border line, until a line with full content is met, and remains in this line'''
    def scanUntilContent(self) -> None:
        self.scanUntil(255-tol,255)


class CropPicture:
    def __init__(self,image:np.ndarray) -> None:
        self.image=image
        height=int(self.image.shape[0])
        width=int(self.image.shape[1])
        self.TopBorder=Border(lambda i:image[i,:])
        self.BottomBorder=Border(lambda i:image[height-1-i,:])
        self.LeftBorder=Border(lambda i:image[:,i])
        self.RightBorder=Border(lambda i:image[:,width-1-i])
        '''Clean the white margin'''
        self.TopBorder.scanUntilContent()
        self.BottomBorder.scanUntilContent()
        self.LeftBorder.scanUntilContent()
        self.RightBorder.scanUntilContent()


    '''Set the cropbox of PyPDF2 according to the four border line'''
    def setCropBox(self,box):
        height=int(self.image.shape[0])
        width=int(self.image.shape[1])
        pdfWidth =int(box.getUpperRight()[0])
        pdfHeight=int(box.getUpperRight()[1])
        box.lowerLeft  = (
            (self.LeftBorder.cur/width)*pdfWidth,
            (1-(self.TopBorder.cur/height))*pdfHeight
        )
        box.upperRight = (
            (1-(self.RightBorder.cur/width))*pdfWidth,
            (self.BottomBorder.cur/height)*pdfHeight
        )

'''Strategy for cropping'''
def process(i:int, image: NDArray, page) -> list :
    pic=CropPicture(image)
    if i==0:
        pic.BottomBorder.scanUntilEmpty()
        pic.BottomBorder.scanUntilContent()
    else:
        pic.TopBorder.scanUntilEmpty()
        pic.TopBorder.scanUntilContent()
    pic.setCropBox(page.cropBox)
    return [page]

'''RuleCrop the file, and save to PdfFileWriter'''
def work(inFilePath:str, outFile:PdfFileWriter):
    images = convert_from_path(inFilePath,grayscale=True)
    inFile = PdfFileReader(open(inFilePath,"rb"))
    for i in range(len(images)):
        for p in process(i,np.array(images[i]),inFile.getPage(i)):
            outFile.addPage(p)

'''RuleCrop the file'''
def workFile(inFilePath:str, outFilePath:str):
    outFile= PdfFileWriter()
    work(inFilePath,outFile)
    with open(outFilePath,'wb') as outStream: outFile.write(outStream) 

'''RuleCrop the file in every folder'''
def workFolder(inFolderPath:str, outFolderPath:str):
    for inFileName in os.listdir(inFolderPath):
        workFile(inFolderPath+"/"+inFileName, outFolderPath+"/"+inFileName)

'''For all pdfs in the folder, in the order of the integer they contain,
- RuleCrop
- Merge into one pdf
- Add a bookmark
'''
def workFolderAndMerge(inFolderPath:str, outFilePath:str):
    outFile= PdfFileWriter()
    pdfList=sorted(
        os.listdir(inFolderPath),
        key=lambda s:int(re.sub('\D', '', s))
    )
    for fileName in pdfList:
        print("Start: "+fileName)
        nPageBefore=outFile.getNumPages()
        work(inFolderPath+"/"+fileName,outFile)
        pdfName=fileName.split("/")[-1].split(".")[0]
        outFile.addBookmark(pdfName,nPageBefore , parent=None)
    print("Saving")
    with open(outFilePath,'wb') as outStream: outFile.write(outStream) 

#workFile("./in/1.pdf","./out/1.pdf")
workFolder("./in","./out/")
workFolderAndMerge("./in","./out/1.pdf")