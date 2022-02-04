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
        self.cur=0
        self.scan=f
    
    def scanUntil(self,l,r) -> None:
        while(inRange(np.average(self.scan(self.cur)),l,r)): 
            self.cur+=1
    
    def scanUntilEmpty(self) -> None:
        self.scanUntil(0,255-tol)
    
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
    pic.TopBorder.scanUntilContent()
    pic.BottomBorder.scanUntilContent()
    pic.LeftBorder.scanUntilContent()
    pic.RightBorder.scanUntilContent()
    if i==0:
        pic.BottomBorder.scanUntilEmpty()
        pic.BottomBorder.scanUntilContent()
    else:
        pic.TopBorder.scanUntilEmpty()
        pic.TopBorder.scanUntilContent()
    pic.setCropBox(page.cropBox)
    return [page]

def work(inFilePath:str, outFile:PdfFileWriter):
    images = convert_from_path(inFilePath,grayscale=True)
    inFile = PdfFileReader(open(inFilePath,"rb"))
    for i in range(len(images)):
        for p in process(i,np.array(images[i]),inFile.getPage(i)):
            outFile.addPage(p)


def workFile(inFilePath:str, outFilePath:str):
    outFile= PdfFileWriter()
    work(inFilePath,outFile)
    with open(outFilePath,'wb') as outStream: outFile.write(outStream) 

def workFolderAndMerge(inFolderPath:str, outFilePath:str):
    outFile= PdfFileWriter()
    pdfList=sorted(
        os.listdir(inFolderPath),
        key=lambda s:int(re.sub('\D', '', s))
    )
    for inFilePath in pdfList:
        print("Start: "+inFilePath)
        nPageBefore=outFile.getNumPages()
        work(inFolderPath+"/"+inFilePath,outFile)
        fileName=inFilePath.split("/")[-1].split(".")[0]
        outFile.addBookmark(fileName,nPageBefore , parent=None)
    print("Saving")
    with open(outFilePath,'wb') as outStream: outFile.write(outStream) 

#workFile("./in/1.pdf","./out/1.pdf")
workFolderAndMerge("./in","./out/1.pdf")