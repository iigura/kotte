# kotte = Kanji Oriented Tiny Text Editor by Koji Iigura, 2025.
import sys,os,subprocess,termios,signal,curses,unicodedata,hashlib

ESC='\x1b'; CR='\n'; DEL='\x7f'
CtrlD='\x04';CtrlE='\x05';CtrlQ='\x11';CtrlR='\x12';CtrlS='\x13'
CtrlU='\x15';CtrlY='\x19'
TabSize=4

Buf=[];Attr=[];Done=False;SavedHash=None
AbsFilePath=FilePathForDisp=None
Index=PageStart=PageEnd=Row=Col=TargetCol=0
SelectionBasePoint=-1; LastIndexForDisplay=None; InfoStr=''
SearchStr=None
StdScr=None

charWidth=lambda x,c: TabSize-x%TabSize if c=='\t' \
          else 2 if unicodedata.east_asian_width(c) in 'WF' else 1

def getNextPos(p,x,y):
    if p==len(Buf): w=1
    else:
        c=Buf[p]
        if c=='\n': return (0,y+1)
        w=charWidth(x,c)
    newX,newY=(x+w,y) if x+w<curses.COLS else (0,y+1)
    if p+1<len(Buf):
        if newX+charWidth(newX,Buf[p+1])>curses.COLS:
            newX=0; newY+=1
    return newX,newY

def getCol0Index(scanStartOffset):
    p=scanStartOffset
    while p>0 and Buf[p-1]!='\n': p-=1
    return p

def getCol(targetIndex):
    p=getCol0Index(targetIndex)
    if p==targetIndex: return 0
    x=0; dummyY=-1 
    while p<targetIndex: x,_=getNextPos(p,x,dummyY); p+=1
    return x

def lineTop(scanStartOffset):
    if scanStartOffset<=0: return 0
    if Buf[scanStartOffset-1]=='\n': return scanStartOffset
    x=0; lineTopIndex=p=getCol0Index(scanStartOffset)
    while p<scanStartOffset:
        x,_=getNextPos(p,x,-1) # -1 == dummyY
        if x==0: lineTopIndex=p+1
        p+=1
    return lineTopIndex

def nextLineTop(scanStartOffset):
    if scanStartOffset+1>=len(Buf): return None
    if Buf[scanStartOffset]=='\n':  return scanStartOffset+1
    x=0; p=lineTop(scanStartOffset)
    while p<scanStartOffset: x,_=getNextPos(p,x,-1); p+=1
    x,_=getNextPos(p,x,-1); p+=1 # -1 == dummyY
    if p>=len(Buf): return None
    while x!=0 and p<len(Buf): x,_=getNextPos(p,x,-1); p+=1
    return p if p<len(Buf) else None          

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

isSelected=lambda: SelectionBasePoint>=0

def Select():
    global SelectionBasePoint,LastIndexForDisplay
    if not isSelected():
        SelectionBasePoint=LastIndexForDisplay=Index
    else:
        clearSelectAreaAttr(Index); SelectionBasePoint=-1

def Display(statusLine=None):
    global PageEnd,LastIndexForDisplay,InfoStr,Row,Col
    assert Index>=PageStart,f"Index={Index} PageStart={PageStart}"
    assert len(Buf)==len(Attr),f"Buf={len(Buf)} Attr={len(Attr)}"
    if SelectionBasePoint>=0:
        clearSelectAreaAttr(LastIndexForDisplay)
        setSelectAreaAttr(Index)
        LastIndexForDisplay=Index
    StdScr.clear(); StdScr.move(0,0); x=y=0
    p=PageStart
    while not(curses.LINES-2<=y or len(Buf)<=p):
        c=Buf[p]; a=Attr[p]
        if p==Index: cursorX=x;cursorY=y
        if c=='\n': y+=1; x=0
        else:
            w=charWidth(x,c)
            if x+w<=curses.COLS: StdScr.addstr(y,x,c,a)
            else: p-=1 # redo Buf[p]
            x+=w
        if x>=curses.COLS: y+=1; x=0
        p+=1
    PageEnd=p-1

    if len(Buf)==0: Row,Col=0,0
    elif Index>=len(Buf): Row,Col=y,x
    else: Row,Col=cursorY,cursorX

    if statusLine is None:
        statusLine=FilePathForDisp
        if isDirty(): statusLine+='(*)'
    posInfo=f" Row:{Row} Col:{Col} "
    totalWidth=curses.COLS
    numOfMiddleSpace=totalWidth-len(statusLine)-len(posInfo)
    s=statusLine+' '*numOfMiddleSpace+posInfo
    StdScr.addstr(curses.LINES-2,0,s,curses.A_REVERSE)

    StdScr.addstr(curses.LINES-1,0,InfoStr)
    InfoStr=''
    StdScr.move(Row,Col)
    StdScr.refresh()

def Left():
    global Index,TargetCol,PageStart
    if Index==0: return
    Display(); Index-=1; newX=getCol(Index)
    if newX==curses.COLS-1 and charWidth(newX,Buf[Index])>1: newX=0
    newY=Row if Col>0 else Row-1
    moveOnPrevLine = newY!=Row
    if newY<0: newY=0; PageStart=lineTop(Index)
    TargetCol=newX
    return moveOnPrevLine

def Right():
    global Index,PageStart,TargetCol
    if len(Buf)==0 or Index>=len(Buf): return None
    TargetCol,newY=getNextPos(Index,Col,Row)
    Index+=1
    if newY>=curses.LINES-2:
        newY=curses.LINES-3; PageStart=nextLineTop(PageStart)
    moveOnNextLine = Row<newY
    return moveOnNextLine

def Up():
    global Index,PageStart
    Display(); p=lineTop(Index)
    if p==0: return
    p=lineTop(p-1); x=0; y=Row-1
    while x<=TargetCol and y==Row-1: x,y=getNextPos(p,x,y); p+=1
    Index=p-1; PageStart=min(PageStart,lineTop(Index))

def Down():
    global Index,PageStart
    Display()
    p=Index; x,y=Col,Row
    while p<len(Buf):
        x,y=getNextPos(p,x,y); p+=1
        if y>Row and x>=TargetCol: break
        if y>Row+1: p-=1; break
    Index=p    
    if y>curses.LINES-3: PageStart=nextLineTop(PageStart)

def getFilePathStrForDisp():
    maxlen=curses.COLS//2
    home=os.path.expanduser('~')
    candidate=AbsFilePath
    if AbsFilePath.startswith(home):
        candidate='~'+AbsFilePath[len(home):]
    if len(candidate)<=maxlen: return candidate
    # try using a relative path format
    candidate=os.path.relpath(AbsFilePath,os.getcwd())
    if len(candidate)<=maxlen: return rel
    if len(AbsFilePath)<=maxlen: return text
    return '...'+AbsFilePath[-(maxlen-3):] # with truncation

def isDirty():
    currentHash=hashlib.sha256(''.join(Buf).encode()).digest()
    return SavedHash!=currentHash

def Insert():
    global Index
    while True:
        Display()
        StdScr.addstr(curses.LINES-1,0,'--- INSERT ---')
        StdScr.move(Row,Col); c=StdScr.get_wch()
        if c==ESC: break
        if c==DEL: Left(); Del()
        elif c in Act: Act[c]()
        else:
            Buf.insert(Index,c);Attr.insert(Index,curses.A_NORMAL)
            Right()

def Del():
    global Index
    if len(Buf)==0: return
    if isSelected():
        start,end=getSelectedArea(Index)
        del Buf[start:end+1]; del Attr[start:end+1]
        Index=max(start-1,0); Right()
    else:
        if len(Buf)>0 and Index<len(Buf) and Buf[Index]!=CR:
            del Buf[Index]; del Attr[Index]
            Index=max(min(len(Buf),Index),0)

def input(prompt='',initValue=''):
    y=curses.LINES-1
    buf=list(initValue); x=len(prompt+initValue)
    while True:
        StdScr.move(y,0); StdScr.clrtoeol()      
        s=prompt+''.join(buf)
        StdScr.addstr(y,0,s); StdScr.refresh()
        StdScr.move(y,x); c=StdScr.get_wch()
        if c==ESC: buf=None; break
        if c==CR : break
        if c==curses.KEY_LEFT and x>len(prompt): x-=1
        elif c==curses.KEY_RIGHT and x<len(s): x+=1
        elif c==DEL:
            if x>len(prompt): del buf[x-len(prompt)-1]; x-=1
        elif x<curses.COLS-1: buf.insert(x-len(prompt),c); x+=1
    StdScr.move(y,0); StdScr.clrtoeol()
    return ''.join(buf) if buf is not None else None

def info(msg,waitMsg='(hit any key)'):
    global InfoStr
    y=curses.LINES-1
    StdScr.move(y,0); StdScr.clrtoeol()      
    StdScr.addstr(y,0,msg+waitMsg if waitMsg is not None else '')
    StdScr.refresh()
    if waitMsg is not None: StdScr.get_wch()
    else: InfoStr=msg

def Quit(dummyParam=None):
    global Done
    if dummyParam is not None: info('invalid param (:q!)'); return
    Done=True    

def SafeQuit(dummyParam):
    if dummyParam is not None: info('invalid param (:q)'); return
    if isDirty():
        ans=input('NOT saved. really Quit? (y/n):')
        if ans!='y': return
    Quit()

def updateHash():
    global SavedHash
    SavedHash=hashlib.sha256(''.join(Buf).encode()).digest()

def updateTargetFile(targetFile):
    global AbsFilePath,FilePathForDisp
    AbsFilePath=os.path.abspath(targetFile)
    FilePathForDisp=getFilePathStrForDisp()

def Save(param=None):
    global AbsFilePath,FilePathForDisp
    if param is None:
        if AbsFilePath is None: info('no file name.'); return
        outFilePath=AbsFilePath            
    else:
        p=param.strip().split()
        if len(p)!=1: info('invalid param (:w)'); return
        outFilePath=p[0]; updateTargetFile(outFilePath)
    with open(outFilePath,'w',encoding='utf-8') as f:
        f.write(''.join(Buf))
    info(f"SAVED:[{FilePathForDisp}]",waitMsg=None)
    updateHash()

def SaveAndQuit(dummyParam=None):
    if dummyParam is None:
        if AbsFilePath is None: info('no file name.'); return
        Save(); Quit()
    else: info('invalid param (:wq)')

def Load(param):
    global AbsFilePath,FilePathForDisp,Buf,Attr,Index,PageStart
    if len(Buf)>0 and isDirty():
        info('current buffer is not saved.'); return
    if param is None:
        AbsFilePath=None; FilePathForDisp='[NEW FILE]'
    else:
        p=param.strip().split()
        if len(p)!=1: info('invalid param (:e)'); return
        filePath=p[0]
        updateTargetFile(filePath)
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
    else: info(f"no such command [{cmd}].")
    
def Colon():
    s=input('',':')
    if s is not None: doColonCmd(s)

def LineBegin():
    global Index,TargetCol
    Index=lineTop(Index); TargetCol=0

def deleteLine(indexOfTheTargetLine):
    global Index
    if isSelected():
        start,end=getSelectedArea(Index); end+=1; Select()
    else:
        start=lineTop(indexOfTheTargetLine)
        end=nextLineTop(indexOfTheTargetLine)
    if end is None: del Buf[Index:]; del Attr[Index:]
    else: del Buf[start:end]; del Attr[start:end]
    Index=max(start-1,0); LineBegin()
    row=Row; Display()
    if row>Row: Down()

isWordBoundary=lambda c:unicodedata.category(c)[0] in 'ZPS'

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
    del Buf[startIndex:end]; del Attr[startIndex:end]

def ScrollUp():
    global PageStart
    if PageEnd+1>=len(Buf): return
    p=nextLineTop(PageStart)
    if Index<p: Down()
    PageStart=p

def ScrollDown():
    global PageStart
    if PageStart==0: return
    if lineTop(Index)>=lineTop(PageEnd): Up()    
    PageStart=lineTop(PageStart-1)

def SearchNext():
    if SearchStr is None: return
    global Index
    s=list(SearchStr)
    for i in range(Index+1,len(Buf)-len(s)+1):
        if Buf[i:i+len(s)]==s:
            if i>=PageEnd:
                while i>=PageEnd: Down()
                ScrollDown()
            Index=i; return

def SearchPrev():
    if SearchStr is None: return
    global Index
    s=list(SearchStr)
    for i in range(Index-1,-1,-1):
        if Buf[i:i+len(s)]==s:
            if i<PageStart:
                while i<PageStart: Up()
            Index=i; return

def Search():
    global SearchStr
    s=input('','/')
    if s is not None: SearchStr=s[1:]; SearchNext()

# high-level functions built on core functions
def LineEnd():
    Display(); y=Row
    while y==Row and (Right() is not None): Display()
    if y<Row: Left()
def Top():global Index,PageStart; Index=PageStart=0
def Bottom():
    global PageStart,Index
    Index=PageStart=lineTop(len(Buf)-1); Display()
    for i in range(curses.LINES-3): Up()
    Index=PageEnd    
def ScreenTop(): global Index; Index=PageStart
def ScreenBottom(): global Index; Index=lineTop(max(PageEnd-1,0))
def PageUp():
    for i in range(curses.LINES//2): ScrollUp(); Down()
def PageDown():
    for i in range(curses.LINES//2): ScrollDown(); Up()
def WordForward():
    global Index,TargetCol
    Index=nextWord(Index); Display(); TargetCol=Col
def WordBackward():
    global Index,TargetCol
    Index=prevWord(Index); Display(); TargetCol=Col
def Join():
    p=Index; LineEnd()
    while Buf[p]!=CR and p<len(Buf): p+=1
    if p<len(Buf) and Buf[p]==CR: Buf[p]=' '
def InsertLineBelow():
    LineEnd(); Display()
    Buf.insert(Index,'\n'); Attr.insert(Index,curses.A_NORMAL)
    Right(); Display(); Insert()
def InsertLineAbove():
    if lineTop(Index)==0: Buf.insert(0,'\n')
    else: Up(); InsertLineBelow()
def Append():
    if 0<=Index<len(Buf) and Buf[Index]!='\n': Right()
    Insert()
def Replace():
    info('(replace to)',waitMsg=None); Display()
    c=StdScr.get_wch()
    if isSelected():
        start,end=getSelectedArea(Index)        
        Buf[start:end+1]=[c]*(end+1-start)
        Select()
    else:
        if 0<=Index<len(Buf): Buf[Index]=c
def ForcusCenterRow():
    global PageStart
    Display()
    targetRow=(curses.LINES-3)//2
    if targetRow==Row: return
    if Row<targetRow:
        while Row<targetRow and PageStart>0:
            PageStart=lineTop(PageStart-1); Display()
    else:
        while Row>targetRow:
            if lineTop(PageEnd)==lineTop(PageStart): break
            PageStart=nextLineTop(PageStart); Display()
def getSecondKey(infoMsg):
    info(infoMsg,waitMsg=None); Display()
    return StdScr.get_wch()
def Prefix_d():
    c=getSecondKey('(Prefix d)')
    if c=='d': deleteLine(Index)
    elif c=='w': deleteWord(Index)
def Prefix_z():
    c=getSecondKey('(Prefix z)')
    if c=='z': ForcusCenterRow()
def PrefixZ():
    c=getSecondKey('(Prefix Z)')
    if c=='Z': SaveAndQuit()

Act={curses.KEY_LEFT :Left,curses.KEY_RIGHT :Right,
     curses.KEY_UP   :Up,  curses.KEY_DOWN  :Down,
     curses.KEY_SLEFT:LineBegin,curses.KEY_SRIGHT:LineEnd,
     CtrlE:ScrollUp,CtrlY:ScrollDown,CtrlU:PageDown,CtrlD:PageUp, }

Cmd={'h':Left,'l':Right,'k':Up,'j':Down,'v':Select,
     '0':LineBegin,'$':LineEnd,'g':Top,'G':Bottom,
     'H':ScreenTop,'L':ScreenBottom,':':Colon,
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
    global StdScr,AbsFilePath,FilePathForDisp,Buf,Attr,SavedHash
    StdScr=stdscr
    Load(targetFilePath)
    curses.raw()
    while not Done:
        Display()
        c=stdscr.get_wch()
        if   c in Act: Act[c]()
        elif c in Cmd: Cmd[c]()

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

