# kotte = Kanji Oriented Tiny Text Editor by Koji Iigura, 2025 - 2026.

import sys,os,subprocess,termios,signal,curses,unicodedata,hashlib

ESC='\x1b'; CR='\n'; DEL='\x7f'
CtrlD='\x04';CtrlE='\x05';CtrlQ='\x11';CtrlR='\x12';CtrlS='\x13'
CtrlU='\x15';CtrlY='\x19'
TabSize=4

Buf=[]; Attr=[]; Done=False; SavedHash=None
AbsFilePath=FilePathForDisp=None
Index=PageStart=PageEnd=Row=Col=TargetCol=0
UpdateTargetCol=False
SelectionBasePoint=-1; LastIndexForDisplay=None 
SearchStr=None
StdScr=None

def isDirty():
    currentHash=hashlib.sha256(''.join(Buf).encode()).digest()
    return SavedHash!=currentHash

def updateHash():
    global SavedHash
    SavedHash=hashlib.sha256(''.join(Buf).encode()).digest()

def getFilePathStrForDisp():
    maxlen=curses.COLS//2
    home=os.path.expanduser('~')
    candidate=AbsFilePath
    if AbsFilePath.startswith(home):
        candidate='~'+AbsFilePath[len(home):]
    if len(candidate)<=maxlen: return candidate
    relpath=os.path.relpath(AbsFilePath,os.getcwd())
    if len(candidate)<=maxlen: return relpath
    if len(AbsFilePath)<=maxlen: return AbsFilePath
    return '...'+AbsFilePath[-(maxlen-3):] # with truncation

isLastRow=lambda y: y==curses.LINES-3

charWidth=lambda x,c: TabSize-x%TabSize if c=='\t' \
          else 2 if unicodedata.east_asian_width(c) in 'WF' else 1

def top():global Index,PageStart; Index=PageStart=0

def logicalLineTop(scanStartOffset):
    p=scanStartOffset
    while p>0 and Buf[p-1]!='\n': p-=1
    return p

def notice(msg,waitMsg='(hit any key)'):
    y=curses.LINES-1
    StdScr.move(y,0); StdScr.clrtoeol()      
    StdScr.addstr(y,0,msg+(waitMsg if waitMsg is not None else ''))
    StdScr.refresh()
    if waitMsg is not None: StdScr.get_wch()

def info(msg): notice(msg,waitMsg=None); return msg

def getNextPos(p,x,y=-1):
    c=Buf[p] # p shoule be in [0,bufSize))
    if c=='\n': return (0,y+1)
    w=charWidth(x,c)
    newX,newY=(x+w,y) if x+w<curses.COLS else (0,y+1)
    if p+1<len(Buf):
        if newX+charWidth(newX,Buf[p+1])>curses.COLS:
            newX=0; newY+=1
    return newX,newY

def getCol(targetIndex):
    p=logicalLineTop(targetIndex)
    if p==targetIndex: return 0
    x=0
    while p<targetIndex: x,_=getNextPos(p,x); p+=1
    return x

def lineTop(start): # start=scanStartOffset
    if start<=0: return 0
    if Buf[start-1]=='\n': return start
    x=0; lineTopIndex=p=logicalLineTop(min(start,len(Buf)-1))
    while p<start:
        x,_=getNextPos(p,x)
        if x==0: lineTopIndex=p+1
        p+=1
    return lineTopIndex

def nextLineTop(start): # start=scanStartOffset
    if start>=len(Buf)-1: return None
    if Buf[start]=='\n': return start+1
    x=getCol(start); p=start; dy=0
    while (x!=0 or dy==0) and p<len(Buf):
        x,dy=getNextPos(p,x,dy); p+=1
    if dy==0: return None
    return p

def prevLineTop(start):
    p=lineTop(start)
    if p==0: return None
    return lineTop(p-1)

def lineEnd(start):
    p=nextLineTop(start)
    if p is None: return len(Buf)
    return max(0,p-1)

def screenTop(): global Index; Index=PageStart
def screenBottom(): global Index; Index=lineTop(PageEnd)
def scrollDown():
    global PageStart
    if PageStart==0: return
    PageStart=lineTop(PageStart-1)

def updatePageStart():
    global PageStart
    if Index<PageStart: PageStart=lineTop(Index)
    elif PageEnd<Index: PageStart=nextLineTop(PageStart)

def adjustPageStart():
    global PageStart
    PageStart=Index
    for i in range(Row): scrollDown()

isSelected=lambda: SelectionBasePoint>=0
def getSelectedArea(index):
    start=min(index,SelectionBasePoint)
    end  =max(index,SelectionBasePoint)
    return start,end
def clearSelectAreaAttr(index):
    start,end=getSelectedArea(index)
    for i in range(start,end): Attr[i] &= ~curses.A_REVERSE
def setSelectAreaAttr(index):
    start,end=getSelectedArea(index)
    for i in range(start,end): Attr[i] |= curses.A_REVERSE
def Select():
    global SelectionBasePoint,LastIndexForDisplay
    if isSelected():
        clearSelectAreaAttr(Index); SelectionBasePoint=-1
    else:
        SelectionBasePoint=LastIndexForDisplay=Index

def insert(pos,c,a=curses.A_NORMAL):
    if pos is None: Buf.append(c); Attr.append(a)
    else: Buf.insert(pos,c); Attr.insert(pos,a)

def Display(statusLine=None):
    global PageEnd,LastIndexForDisplay,Row,Col,TargetCol
    if isSelected():
        clearSelectAreaAttr(LastIndexForDisplay)
        setSelectAreaAttr(Index)
        LastIndexForDisplay=Index
    x=y=0; p=PageStart; StdScr.clear(); StdScr.move(0,0)
    while y<curses.LINES-2 and p<=len(Buf):
        c,a=(Buf[p],Attr[p]) if p<len(Buf) else (None,None)
        if p==Index: cursorX=x;cursorY=y
        if c=='\n': y+=1; x=0
        elif c is not None:
            w=charWidth(x,c)
            if x+w<=curses.COLS: StdScr.addstr(y,x,c,a)
            else: p-=1 # redo Buf[p]
            x+=w
        if x>=curses.COLS: y+=1; x=0
        p+=1
    PageEnd=p-1; filledRow = y>=curses.LINES-3
    Row,Col=cursorY,cursorX
    if UpdateTargetCol: TargetCol=Col

    if statusLine is None:
        statusLine=FilePathForDisp
        if isDirty(): statusLine+='(*)'
    posInfo=f" Row:{Row} Col:{Col} "
    totalWidth=curses.COLS
    numOfMiddleSpace=totalWidth-len(statusLine)-len(posInfo)
    s=statusLine+' '*numOfMiddleSpace+posInfo
    StdScr.addstr(curses.LINES-2,0,s,curses.A_REVERSE)

    StdScr.move(Row,Col)
    StdScr.refresh()
    return filledRow

def moveH(delta):
    global Index,UpdateTargetCol
    p=max(0,min(len(Buf),Index+delta))
    if p!=Index:
        Index=p; updatePageStart(); UpdateTargetCol=True
Left =lambda: moveH(-1)
Right=lambda: moveH(+1)

def moveToTargetCol(lineTopIndex):
    global Index
    e=lineEnd(lineTopIndex)
    for p in range(lineTopIndex,e+1):
        x=getCol(p)
        if x>=TargetCol: break
    Index=p; updatePageStart()

def Up():
    global Index
    s=prevLineTop(Index)
    if s is None: Index=0; return
    moveToTargetCol(s)

def Down():
    global Index,PageStart
    s=nextLineTop(Index)
    if s is None: Index=len(Buf); updatePageStart()
    else: moveToTargetCol(s)

def Del():
    global Index
    if len(Buf)==0: return
    if isSelected():
        start,end=getSelectedArea(Index)
        del Buf[start:end+1]; del Attr[start:end+1]
        Select()
        Index=max(start-1,0); Right()
        adjustPageStart() 
    else:
        if len(Buf)>0 and Index<len(Buf) and Buf[Index]!=CR:
            del Buf[Index]; del Attr[Index]
            Index=max(min(len(Buf),Index),0)

def Insert():
    global Index,PageStart
    info('--- INSERT ---')
    while True:
        filledRow=Display()
        StdScr.move(Row,Col); c=StdScr.get_wch()
        if c==ESC: break
        if c==DEL: Left(); Del()
        elif c in Act: Act[c]()
        elif isinstance(c,str):
            insert(Index,c); Index+=1
            if lineTop(Index)>PageEnd and filledRow:
                PageStart=nextLineTop(PageStart)

def input(prompt='',initValue=''):
    y=curses.LINES-1
    buf=list(initValue); x=len(prompt+initValue); n=len(prompt)
    while True:
        s=prompt+''.join(buf); info(s)
        StdScr.move(y,x); c=StdScr.get_wch()
        if c==ESC: buf=None; break
        if c==CR : break
        if c==curses.KEY_LEFT:
            if x>n: x-=1
        elif c==curses.KEY_RIGHT:
            if x<len(s): x+=1
        elif c==DEL:
            if x>n: del buf[x-n-1]; x-=1
        elif x<curses.COLS-1: buf.insert(x-n,c); x+=1
    StdScr.move(y,0); StdScr.clrtoeol()
    return ''.join(buf) if buf is not None else None

def Quit(dummyParam=None):
    global Done
    if dummyParam is not None:notice('invalid param (:q!)');return
    Done=True    

def SafeQuit(dummyParam): 
    if dummyParam is not None:notice('invalid param (:q)'); return
    if isDirty():
        ans=input('NOT saved. really Quit? (y/n):')
        if ans!='y': return
    Quit()

def updateTargetFile(targetFile):
    global AbsFilePath,FilePathForDisp
    AbsFilePath=os.path.abspath(targetFile)
    FilePathForDisp=getFilePathStrForDisp()

def Save(param=None):
    global AbsFilePath,FilePathForDisp
    if param is None:
        if AbsFilePath is None: notice('no file name.'); return
        outFilePath=AbsFilePath            
    else:
        p=param.strip().split()
        if len(p)!=1: notice('invalid param (:w)'); return
        outFilePath=p[0]; updateTargetFile(outFilePath)
    with open(outFilePath,'w',encoding='utf-8') as f:
        f.write(''.join(Buf))
    info(f"SAVED:[{FilePathForDisp}]")
    updateHash()

def SaveAndQuit(dummyParam=None):
    if dummyParam is None:
        if AbsFilePath is None: notice('no file name.'); return
        Save(); Quit()
    else: notice('invalid param (:wq)')

def Load(param):
    global AbsFilePath,FilePathForDisp,Buf,Attr,Index,PageStart
    if len(Buf)>0 and isDirty():
        notice('current buffer is not saved.')
    elif param is None:
        AbsFilePath=None; FilePathForDisp='[NEW FILE]'
        Buf=[]; Attr=[]
    else:
        p=param.strip().split()
        if len(p)!=1: notice('invalid param (:e)'); return
        filePath=p[0]; updateTargetFile(filePath)
        with open(AbsFilePath) as f: Buf=list(f.read())
        Attr=[curses.A_NORMAL for i in range(len(Buf))]
        Index=PageStart=0
    updateHash()

ColonCmd={':q':SafeQuit,':q!':Quit,':w':Save,':wq':SaveAndQuit,
          ':e':Load}

def doColonCmd(cmdStr):
    tokens=cmdStr.strip().split(maxsplit=1)
    if len(tokens)==0: return    
    cmd=tokens[0]
    param=tokens[1] if len(tokens)>1 else None
    if cmd in ColonCmd: ColonCmd[cmd](param)
    else: notice(f"no such command [{cmd}].")
    
def Colon():
    s=input('',':')
    if s is not None: doColonCmd(s)

def LineBegin():
    global Index,UpdateTargetCol
    Index=lineTop(Index); UpdateTargetCol=True

def deleteLine():
    global Index,PageStart
    if isSelected():
        start,end=getSelectedArea(Index); end+=1; Select()
    else:
        start=lineTop(Index); end=nextLineTop(Index)
    if end is None: del Buf[Index:]; del Attr[Index:]
    else: del Buf[start:end]; del Attr[start:end]
    Index=max(start-1,0); LineBegin(); Down()
    adjustPageStart()

def isWordBoundary(c):
    return c in '\n\t' or unicodedata.category(c)[0] in 'ZPS'

def nextWord(startIndex):
    if startIndex>=len(Buf): return len(Buf)
    p=startIndex
    if isWordBoundary(Buf[p]):
        while p<len(Buf) and isWordBoundary(Buf[p]): p+=1
    else:
        while p<len(Buf) and isWordBoundary(Buf[p])==False: p+=1
        p=nextWord(p) if p<len(Buf) else len(Buf)
    return p

def prevWord(startIndex):
    p=lineTop(startIndex-1)
    while (q:=nextWord(p))<startIndex: p=q  
    return p

def deleteWord(startIndex):
    end=nextWord(startIndex)
    del Buf[startIndex:end-1]; del Attr[startIndex:end-1]

def wordMove(func):
    global Index,UpdateTargetCol
    Index=func(Index); UpdateTargetCol=True
WordForward =lambda: wordMove(nextWord)
WordBackward=lambda: wordMove(prevWord)

def ScrollUp():
    global PageStart
    if PageEnd>=len(Buf): return
    p=nextLineTop(PageStart)
    if Index<p: Down()
    PageStart=p
 
def ScrollDown():
    oldPS=PageStart; scrollDown()
    if oldPS!=PageStart and Row>=curses.LINES-3: Up()

def search(targetRange):
    if SearchStr is None: return
    global Index; s=list(SearchStr)
    for i in targetRange:
        if Buf[i:i+len(s)]==s:
            Index=i
            if i<PageStart or PageEnd<i: adjustPageStart()
            return
    return info(f"pattern not found: {SearchStr}")
def SearchNext():
    if SearchStr is not None:
        return search(range(Index+1,len(Buf)-len(SearchStr)+1))
def SearchPrev():search(range(Index-1,-1,-1))
def Search():
    global SearchStr; s=input('','/')
    if s is not None: SearchStr=s[1:]; return SearchNext()

def LineEnd(): global Index; Index=lineEnd(Index)

def Bottom():
    global Index,Row
    Index=lineTop(len(Buf)); Row=curses.LINES-3; adjustPageStart()

def PageUp():
    for i in range(curses.LINES//2): ScrollUp(); Down()
def PageDown():
    for i in range(curses.LINES//2): scrollDown(); Up()

def Join():
    p=Index; LineEnd()
    while Buf[p]!=CR and p<len(Buf): p+=1
    if p<len(Buf) and Buf[p]==CR: Buf[p]=' '

def InsertLineBelow():
    global Index
    p=nextLineTop(Index)
    if not (Col==0 and p is None):
        insert(p,'\n'); Index=len(Buf)-1 if p is None else p
        updatePageStart()
    Insert()

def InsertLineAbove():
    global Index
    if lineTop(Index)==0:
        Buf.insert(0,'\n'); Attr.insert(0,curses.A_NORMAL)
        Index=0; Insert()
    else: Up(); InsertLineBelow()

def Append():
    if 0<=Index<len(Buf) and Buf[Index]!='\n': Right()
    Insert()

def Replace():
    info('(replace to) '); c=StdScr.get_wch()
    if c==ESC: return
    if isSelected():
        start,end=getSelectedArea(Index)        
        Buf[start:end+1]=[c]*(end+1-start)
        Select()
    else:
        if 0<=Index<len(Buf): Buf[Index]=c

def FocusCenterRow():
    global Row; Row=(curses.LINES-3)//2; adjustPageStart()

def getSecondKey(infoMsg):
    info(infoMsg)
    return StdScr.get_wch()
def Prefix_d():
    c=getSecondKey('(Prefix d)')
    if c=='d': deleteLine()
    elif c=='w': deleteWord(Index)
def Prefix_z():
    c=getSecondKey('(Prefix z)')
    if c=='z': FocusCenterRow()
def PrefixZ():
    c=getSecondKey('(Prefix Z)')
    if c=='Z': SaveAndQuit()

Act={curses.KEY_LEFT :Left,curses.KEY_RIGHT :Right,
     curses.KEY_UP   :Up,  curses.KEY_DOWN  :Down,
     curses.KEY_SLEFT:LineBegin,curses.KEY_SRIGHT:LineEnd,
     CtrlE:ScrollUp,CtrlY:ScrollDown,CtrlU:PageDown,CtrlD:PageUp,
}

Cmd={'h':Left,'l':Right,'k':Up,'j':Down,'v':Select,
     '0':LineBegin,'$':LineEnd,'g':top,'G':Bottom,
     'H':screenTop,'L':screenBottom,':':Colon,
     'w':WordForward,'b':WordBackward,'i':Insert,'a':Append,
     'o':InsertLineBelow,'O':InsertLineAbove,
     '/':Search,'n':SearchNext,'N':SearchPrev,
     'r':Replace,'x':Del,'J':Join,
     'd':Prefix_d,'z':Prefix_z,'Z':PrefixZ, }

def disableFlowControl():
    result=subprocess.run(['stty','-g'],
                          capture_output=True,text=True)
    originalSettings=result.stdout.strip()
    subprocess.run(['stty','-ixon','dsusp','undef'])
    return originalSettings

def restoreStty(originalSettings):
    subprocess.run(['stty',originalSettings])

def disableCtrlC():
    fd=sys.stdin.fileno()
    originalTermios=termios.tcgetattr(fd)
    newTermios=originalTermios[:]
    newTermios[3] &= ~(termios.ISIG|termios.ICANON|termios.ECHO)
    termios.tcsetattr(fd,termios.TCSADRAIN,newTermios)
    originalSigint=signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGINT,signal.SIG_IGN)
    return originalTermios,originalSigint

def restoreCtrlC(originalTermios,originalSigint):
    fd=sys.stdin.fileno()
    termios.tcsetattr(fd,termios.TCSADRAIN,originalTermios)
    signal.signal(signal.SIGINT,originalSigint)

def Main(stdscr,targetFilePath):
    global UpdateTargetCol,StdScr; StdScr=stdscr
    Load(targetFilePath); curses.raw(); infoStr=None
    while not Done:
        Display(); UpdateTargetCol=False
        if infoStr is not None: info(infoStr)
        c=stdscr.get_wch()
        if   c in Act: infoStr=Act[c]()
        elif c in Cmd: infoStr=Cmd[c]()

def kotte(targetFilePath):
    originalTermios,originalSigint=disableCtrlC()
    originalSettings=disableFlowControl()
    os.environ.setdefault('ESCDELAY','1')
    try:
        curses.wrapper(Main,targetFilePath)
    finally:
        restoreStty(originalSettings)
        restoreCtrlC(originalTermios,originalSigint)

if __name__ == "__main__":
    targetFilePath=sys.argv[1] if len(sys.argv)==2 else None
    kotte(targetFilePath)
